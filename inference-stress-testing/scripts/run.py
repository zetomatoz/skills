#!/usr/bin/env python3
"""Portable Docker entrypoint: plan, probe, warm up, benchmark, evaluate."""
import argparse
import copy
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from workload import build_scenario, describe
from probe import probe
from evaluate import evaluate_report, markdown_summary
from runtime_config import load_environment, inference_environment, trusted_environment, connection_manifest
from scenario import prepare_spec, context_check


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def execute(scenario, folder, env):
    runtime = copy.deepcopy(scenario)
    if env.get("AI_API_KEY"):
        runtime["spec"]["backend"]["api_key"] = env["AI_API_KEY"]
    # Secrets appear only in a private temporary file, never in argv or plan.json.
    fd, name = tempfile.mkstemp(prefix="guidellm-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(runtime, stream)
        child_env = dict(env)
        for key in ("PROXY_API_KEY", "INFERENCE_BACKEND_API_KEY", "CONTROL_PLANE_API_KEY",
                    "OPENAI_API_KEY", "AI_API_KEY", "RAY_AUTH_TOKEN"):
            child_env.pop(key, None)
        child_env["GUIDELLM__LOGGING__LOG_FILE"] = str(folder / "guidellm.log")
        result = subprocess.run(["guidellm", "run", "--config", name,
                                 "--disable-console-interactive"], env=child_env)
        if result.returncode:
            raise RuntimeError(f"GuideLLM failed with exit code {result.returncode}")
    finally:
        Path(name).unlink(missing_ok=True)


def validate_native(scenario, env):
    """GuideLLM validates schemas locally before any probe or load is sent."""
    from guidellm.schemas.benchmark.entrypoints import BenchmarkScenario
    try:
        parsed = BenchmarkScenario.model_validate(copy.deepcopy(scenario))
        for benchmark in parsed.get_benchmarks():
            if not any(item.kind in ("max_requests", "max_duration") for item in benchmark.constraints):
                raise ValueError("Unbounded benchmark")
            context_check(benchmark.model_dump(mode="json"), env)
    except Exception:
        raise RuntimeError("GuideLLM rejected the scenario; review the native 0.8.0 schema and stage constraints") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "run"], nargs="?", default="plan")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--spec", type=Path, help="Native GuideLLM JSON/YAML scenario or flat spec")
    parser.add_argument("--env-file", type=Path, help="Dotenv file (default: optional .env); process variables win")
    parser.add_argument("--run-name", help="Label appended to the fresh artifact directory")
    args = parser.parse_args(argv)
    if args.run_name:
        import re
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run_name):
            parser.error("--run-name must contain 1-80 letters, digits, dots, underscores or hyphens")
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if args.run_name:
        label += "-" + args.run_name
    folder = (args.output or Path("artifacts") / label).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.chmod(folder, 0o700)
    status = {"status": "PLANNED", "live_benchmark_run": False}
    try:
        env = trusted_environment(load_environment(args.env_file))
        if args.spec:
            scenario, manifest, env = prepare_spec(args.spec, env, folder)
        else:
            env = inference_environment(env)
            scenario = build_scenario(env, folder)
            manifest = describe(env)
            manifest.update(workload_source="generated_mix", connections=connection_manifest(env))
        if args.run_name:
            scenario.setdefault("metadata", {}).setdefault("labels", {})["run_name"] = args.run_name
            manifest["run_name"] = args.run_name
        save(folder / "scenario.json", scenario)
        save(folder / "manifest.json", manifest)
        print(f"Plan saved: {folder}", flush=True)
        if args.action == "plan":
            return 0
        version = importlib.metadata.version("guidellm")
        if version != "0.8.0":
            raise RuntimeError(f"Expected tested GuideLLM 0.8.0; found {version}")
        validate_native(scenario, env)
        save(folder / "versions.json", {"guidellm": version, "python": sys.version,
                                       "image": env.get("GUIDELLM_IMAGE", "ghcr.io/vllm-project/guidellm:v0.8.0")})
        checks = probe(env)
        save(folder / "quality.json", checks)
        if checks["status"] != "PASS":
            raise RuntimeError("Endpoint/correctness smoke failed; see quality.json")
        try:
            seconds = int(env.get("WARMUP_SECONDS", "15"))
        except ValueError:
            raise ValueError("WARMUP_SECONDS must be a nonnegative integer") from None
        if seconds < 0:
            raise ValueError("WARMUP_SECONDS must be nonnegative")
        if seconds:
            warm_dir = folder / "warmup"
            warm_dir.mkdir()
            warmup = copy.deepcopy(scenario)
            warmup.pop("benchmarks", None)
            warmup["spec"]["profile"] = {"kind": "concurrent", "streams": [1]}
            # A finite loader can exhaust before a duration-only run observes its
            # deadline. Keep the request bound so short specs complete cleanly.
            bounds = [item for item in scenario["spec"].get("constraints", [])
                      if item.get("kind") == "max_requests"]
            samples = scenario["spec"].get("data_loader", {}).get("samples")
            if not bounds and isinstance(samples, int) and samples > 0:
                bounds = [{"kind": "max_requests", "count": samples}]
            warmup["spec"]["constraints"] = bounds + [{"kind": "max_duration", "seconds": seconds}]
            warmup["spec"]["outputs"] = [{"kind": "json", "path": str(warm_dir / "benchmarks.json")}]
            print("Running separate warmup…", flush=True)
            execute(warmup, warm_dir, env)
        print("Running measured workload…", flush=True)
        status["live_benchmark_run"] = True
        execute(scenario, folder, env)
        report = json.loads((folder / "benchmarks.json").read_text())
        evaluation = evaluate_report(report, env)
        save(folder / "evaluation.json", evaluation)
        (folder / "summary.md").write_text(markdown_summary(evaluation))
        status["status"] = evaluation["status"]
        print(f"{status['status']}: {folder / 'summary.md'}", flush=True)
        return 0 if status["status"] == "PASS" else 2
    except Exception as exc:
        status.update(status="FAIL", error_type=type(exc).__name__)
        if isinstance(exc, (ValueError, RuntimeError)):
            status["error"] = str(exc)
        # All raised local validation messages are safe; never print API bodies.
        print(f"Run failed ({type(exc).__name__}): {status.get('error', 'see artifacts')} [{folder}]", file=sys.stderr)
        return 2
    finally:
        save(folder / "status.json", status)


if __name__ == "__main__":
    raise SystemExit(main())
