"""Connections, spec preservation, dotenv precedence, TLS, and secret handling."""
import copy
import io
import json
import os
from pathlib import Path
import ssl
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run as runner
from runtime_config import load_environment, inference_environment, trusted_environment, tls_context
from scenario import prepare_spec, context_check
from probe import probe


def native_spec():
    return {"backend": {"kind": "openai_http", "model": "spec-model", "verify": True},
            "tokenizer": {"kind": "huggingface_auto", "model": "test/tokenizer"},
            "profile": {"kind": "concurrent", "streams": [8]},
            "data": [{"kind": "synthetic_text", "turns": 24, "first_prompt_tokens": 100,
                      "prompt_tokens": 10, "output_tokens": 5}],
            "data_loader": {"kind": "pytorch", "samples": 8},
            "constraints": [{"kind": "max_requests", "count": 192},
                            {"kind": "max_duration", "seconds": 5400}]}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env = {"BENCH_TARGET": "proxy", "ENDPOINT_PROXY": "https://proxy.example/v1",
                    "PROXY_API_KEY": "proxy-secret", "AI_API_KEY": "legacy-secret",
                    "ENDPOINT_INFERENCE_BACKEND": "https://backend.example/v1",
                    "INFERENCE_BACKEND_API_KEY": "backend-secret", "OPENAI_API_KEY": "openai-secret",
                    "ENDPOINT_CONTROL_PLANE": "https://control.example", "CONTROL_PLANE_API_KEY": "admin-secret",
                    "AI_MODEL": "legacy-model", "STREAMS": "12,24"}

    def test_target_specific_auth_and_legacy_compatibility(self):
        for name, url, key in (("proxy", "https://proxy.example", "proxy-secret"),
                              ("inference_backend", "https://backend.example", "backend-secret"),
                              ("openai", "https://api.openai.com", "openai-secret")):
            with self.subTest(name=name):
                selected = inference_environment(dict(self.env, BENCH_TARGET=name))
                self.assertEqual((selected["AI_ENDPOINT"], selected["AI_API_KEY"]), (url, key))
        legacy = inference_environment({"AI_ENDPOINT": "http://localhost:8000/v1", "AI_MODEL": "test", "AI_API_KEY": "old"})
        self.assertEqual(legacy["AI_API_KEY"], "old")
        no_key = inference_environment(dict(self.env, PROXY_API_KEY=""))
        self.assertEqual(no_key["AI_API_KEY"], "")
        with self.assertRaises(ValueError):
            inference_environment(dict(self.env, ENDPOINT_PROXY=""))
        with self.assertRaises(ValueError):
            inference_environment(dict(self.env, BENCH_TARGET="secret-value"))

    def test_dotenv_process_precedence_quotes_comments_and_literal_windows_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "runtime.env"
            source.write_text('PROXY_API_KEY="file#secret" # comment\nAI_MODEL=from-file\n'
                              'export HF_TOKEN=token#suffix\nCERT_FILE=C:\\certs\\ca.pem\nEMPTY=\n')
            env = load_environment(source, {"PROXY_API_KEY": "process-secret", "EMPTY": ""})
            self.assertEqual(env["PROXY_API_KEY"], "process-secret")
            self.assertEqual(env["AI_MODEL"], "from-file")
            self.assertEqual(env["HF_TOKEN"], "token#suffix")
            self.assertEqual(env["CERT_FILE"], r"C:\certs\ca.pem")
            source.write_text('PROXY_API_KEY="secret-unclosed\n')
            with self.assertRaises(ValueError) as error:
                load_environment(source, {})
            self.assertNotIn("secret-unclosed", str(error.exception))

    def test_native_flat_and_wrapped_specs_preserve_workload_and_choose_spec_model(self):
        for wrapped in (False, True):
            with self.subTest(wrapped=wrapped), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "spec.json"
                original = native_spec()
                source.write_text(json.dumps({"spec": original} if wrapped else original))
                scenario, manifest, env = prepare_spec(source, self.env, Path(directory))
                for field in ("tokenizer", "profile", "data", "data_loader", "constraints"):
                    self.assertEqual(scenario["spec"][field], original[field])
                self.assertEqual(scenario["spec"]["backend"]["target"], "https://proxy.example")
                self.assertEqual(env["AI_MODEL"], "spec-model")
                serialized = json.dumps([scenario, manifest])
                for secret in ("proxy-secret", "backend-secret", "admin-secret", "legacy-secret", "openai-secret"):
                    self.assertNotIn(secret, serialized)
                self.assertFalse(manifest["connections"]["control_plane_used_by_benchmark"])
                self.assertEqual(json.loads(source.read_text()), {"spec": original} if wrapped else original)

    def test_yaml_and_relative_trace_paths(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is supplied by GuideLLM and installed in CI")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spec.yaml"
            original = native_spec()
            original["data"] = [{"kind": "trace_synthetic", "source": {"kind": "csv_file", "path": "trace.csv"}}]
            original["tokenizer"]["model"] = "./tokenizer"
            source.write_text(yaml.safe_dump(original))
            scenario, _, _ = prepare_spec(source, self.env, Path(directory))
            self.assertEqual(scenario["spec"]["data"][0]["source"]["path"], str((Path(directory) / "trace.csv").resolve()))
            self.assertEqual(scenario["spec"]["tokenizer"]["model"], str((Path(directory) / "tokenizer").resolve()))

    def test_rejects_embedded_auth_insecure_tls_unbounded_load_and_backend_overrides(self):
        for change in ("key", "tls", "bounds", "override"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                original = native_spec()
                if change == "key":
                    original["backend"]["api_key"] = "secret-in-spec"
                elif change == "tls":
                    original["backend"]["verify"] = False
                elif change == "bounds":
                    original["constraints"] = []
                else:
                    original = {"spec": original, "benchmarks": [{"backend.target": "https://other.example"}]}
                source = Path(directory) / "spec.json"
                source.write_text(json.dumps(original))
                with self.assertRaises(ValueError) as error:
                    prepare_spec(source, self.env, Path(directory))
                self.assertNotIn("secret-in-spec", str(error.exception))

    def test_plan_is_offline_and_artifacts_do_not_contain_secrets(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            source = Path(directory) / "spec.json"
            source.write_text(json.dumps(native_spec()))
            dotenv = Path(directory) / ".env"
            dotenv.write_text("\n".join(f"{key}={value}" for key, value in self.env.items()))
            output = Path(directory) / "result"
            with patch.object(runner, "probe") as probing, patch.object(runner, "execute") as executing, \
                    patch.object(runner.importlib.metadata, "version") as version, \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(runner.main(["plan", "--spec", str(source), "--env-file", str(dotenv),
                                              "--run-name", "first-test", "--output", str(output)]), 0)
                probing.assert_not_called()
                executing.assert_not_called()
                version.assert_not_called()
            self.assertEqual(json.loads((output / "status.json").read_text())["status"], "PLANNED")
            self.assertEqual(json.loads((output / "manifest.json").read_text())["run_name"], "first-test")
            for artifact in output.glob("*.json"):
                self.assertNotIn("secret", artifact.read_text())

    def test_execute_injects_key_privately_and_removes_temporary_file_even_on_failure(self):
        for code in (0, 1):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                original = {"spec": native_spec()}
                snapshot = copy.deepcopy(original)
                captured = []
                env = inference_environment(self.env, original["spec"]["backend"])
                def launch(argv, env):
                    path = Path(argv[argv.index("--config") + 1])
                    captured.append(path)
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(json.loads(path.read_text())["spec"]["backend"]["api_key"], "proxy-secret")
                    self.assertNotIn("proxy-secret", " ".join(argv))
                    for key in ("PROXY_API_KEY", "INFERENCE_BACKEND_API_KEY", "CONTROL_PLANE_API_KEY", "AI_API_KEY"):
                        self.assertNotIn(key, env)
                    return SimpleNamespace(returncode=code)
                with patch.object(runner.subprocess, "run", side_effect=launch):
                    if code:
                        with self.assertRaises(RuntimeError):
                            runner.execute(original, Path(directory), env)
                    else:
                        runner.execute(original, Path(directory), env)
                self.assertFalse(captured[0].exists())
                self.assertEqual(original, snapshot)

    def test_certificate_trust_is_forwarded_and_verification_stays_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "ca.pem"
            certificate.write_text("fixture")
            env = trusted_environment({"CERT_FILE": str(certificate)})
            self.assertEqual(env["SSL_CERT_FILE"], str(certificate.resolve()))
            self.assertEqual(env["REQUESTS_CA_BUNDLE"], str(certificate.resolve()))
            with patch("runtime_config.ssl.create_default_context", wraps=ssl.create_default_context) as create:
                context = tls_context({})
                create.assert_called_once_with(cafile=None)
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            with self.assertRaises(ValueError):
                trusted_environment({"CERT_FILE": str(Path(directory) / "missing.pem")})

    def test_probe_uses_selected_auth_format_route_and_tls_context(self):
        for request_format, response, field in (
                ("/v1/chat/completions", {"choices": [{"message": {"content": "READY"}}]}, "messages"),
                ("/v1/completions", {"choices": [{"text": "READY"}]}, "prompt"),
                ("/v1/responses", {"output": [{"content": [{"type": "output_text", "text": "READY"}]}]}, "input")):
            with self.subTest(format=request_format):
                env = dict(self.env, QUALITY_EVAL="0", PROBE_REQUEST_FORMAT=request_format, PROBE_ROUTE="/custom/generate")
                def request(req, **kwargs):
                    self.assertEqual(req.full_url, "https://proxy.example/custom/generate")
                    self.assertEqual(req.get_header("Authorization"), "Bearer proxy-secret")
                    self.assertIn(field, json.loads(req.data))
                    self.assertTrue(kwargs["context"].check_hostname)
                    return io.BytesIO(json.dumps(response).encode())
                with patch("probe.urllib.request.urlopen", side_effect=request):
                    self.assertEqual(probe(env)["status"], "PASS")

    def test_context_checks_trace_and_accumulated_synthetic_history(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spec.json"
            source.write_text(json.dumps(native_spec()))
            _, manifest, _ = prepare_spec(source, dict(self.env, CONTEXT_TOKENS="1024"), Path(directory))
            self.assertEqual(manifest["context_check"]["status"], "PASS")
            with self.assertRaises(ValueError):
                prepare_spec(source, dict(self.env, CONTEXT_TOKENS="512"), Path(directory))
            original = native_spec()
            original["data"] = [{"kind": "trace_synthetic", "source": {"kind": "csv_file", "path": "trace.csv"}}]
            source.write_text(json.dumps(original))
            (Path(directory) / "trace.csv").write_text("input_length,output_length\n800,100\n")
            with self.assertRaises(ValueError):
                prepare_spec(source, dict(self.env, CONTEXT_TOKENS="1024"), Path(directory))
            schema_defaults = {"data": [{"kind": "synthetic_text", "prompt_tokens": 1000,
                                         "prompt_tokens_max": None, "first_prompt_tokens": None,
                                         "output_tokens": 32, "output_tokens_max": None,
                                         "first_output_tokens": None, "prefix_tokens": None, "turns": 1}]}
            with self.assertRaises(ValueError):
                context_check(schema_defaults, {"CONTEXT_TOKENS": "1024"})

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose unavailable")
    def test_compose_forwards_process_secrets_and_maps_host_certificate_to_container(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for filename in ("compose.yaml", "compose.cert.yaml"):
                shutil.copyfile(ROOT / filename, folder / filename)
            (folder / ".env").write_text("BENCH_TARGET=proxy\nENDPOINT_PROXY=https://proxy.example/v1\n"
                                         "PROXY_API_KEY=file-value\nCERT_FILE=./ca.pem\n")
            (folder / "ca.pem").write_text("fixture")
            env = {"PATH": os.environ["PATH"], "PROXY_API_KEY": "process-value"}
            result = subprocess.run(["docker", "compose", "-f", "compose.yaml", "-f", "compose.cert.yaml",
                                     "config", "--format", "json"], cwd=folder, env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, "Compose configuration failed")
            services = json.loads(result.stdout)["services"]
            for service in services.values():
                self.assertEqual(service["environment"]["PROXY_API_KEY"], "process-value")
                self.assertEqual(service["environment"]["CERT_FILE"], "/certificates/ca.pem")
                certificate = next(volume for volume in service["volumes"] if volume["target"] == "/certificates/ca.pem")
                self.assertTrue(certificate["read_only"])
                self.assertEqual(Path(certificate["source"]).resolve(), (folder / "ca.pem").resolve())


if __name__ == "__main__":
    unittest.main()
