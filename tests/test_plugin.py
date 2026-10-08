import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_plugin", ROOT / "scripts/build_plugin.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
spec = importlib.util.spec_from_file_location("bundle_links", ROOT / "scripts/check_links.py")
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class PluginTests(unittest.TestCase):
    def test_self_contained_bundle_links_commands_imports_and_marketplace(self):
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build(Path(directory) / "inference-engineering", archive=True)
            self.assertEqual(links.check(output)[2], [])
            manifest = json.loads((output / "plugin.json").read_text())
            self.assertEqual(manifest["name"], "inference-engineering")
            self.assertEqual({p.name for p in (output / "skills").iterdir()}, set(builder.SKILLS))
            self.assertEqual(len(list((output / "commands").glob("*.md"))), 4)
            self.assertEqual(manifest["skills"], "./skills/")
            self.assertEqual(manifest["commands"], "./commands/")
            self.assertEqual(manifest["agents"], "./agents/")
            self.assertTrue((output / "skills/inference-stress-testing/compose.cert.yaml").is_file())
            self.assertTrue((output / "skills/inference-stress-testing/assets/specs/smoke.json").is_file())
            self.assertTrue((output / "skills/inference-stress-testing/assets/specs/smoke.yaml").is_file())
            self.assertTrue((output / "skills/inference-stress-testing/assets/workloads/mixed.csv").is_file())
            self.assertNotIn("$schema", manifest)
            self.assertEqual(len(list((output / "agents").glob("*.agent.md"))), 5)
            for script in ("ray-autotune-inference/scripts/ray_control.py",
                           "inference-observability/scripts/collect_metrics.py",
                           "inference-optimization/scripts/compare_runs.py"):
                result = subprocess.run(["python3", str(output / "skills" / script), "--help"], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            market = json.loads((output.parent / ".agents/plugins/marketplace.json").read_text())
            self.assertEqual(market["plugins"][0]["source"]["path"], "./inference-engineering")
            copilot_market = json.loads((output.parent / "marketplace.json").read_text())
            self.assertEqual(copilot_market["plugins"][0]["source"], "./inference-engineering")
            with zipfile.ZipFile(output.with_suffix(".zip")) as archive:
                self.assertIn("inference-engineering/.codex-plugin/plugin.json", archive.namelist())
            with self.assertRaises(ValueError):
                builder.build(output)

    def test_portable_build_keeps_copilot_overlays(self):
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build(Path(directory) / "inference-engineering", format="portable")
            manifest = json.loads((output / "plugin.json").read_text())
            self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
            self.assertNotIn("agents", manifest)
            self.assertEqual(len(list((output / "com.github.copilot/agents").glob("*.agent.md"))), 5)
            self.assertEqual(len(list((output / "com.github.copilot/commands").glob("*.md"))), 4)
            self.assertEqual(links.check(output)[2], [])

    def test_runtime_and_private_files_excluded(self):
        for value in (".env", "serve.json", "artifacts/run.json", "scripts/__pycache__/ray.pyc",
                      "references/.secret.json", ".git/config", "workload.csv", "assets/certs/company.pem",
                      "assets/specs/.private.json", "assets/local-settings.json"):
            self.assertFalse(builder.included(Path(value)), value)
        self.assertTrue(builder.included(Path(".env.example")))
        self.assertTrue(builder.included(Path("scripts/ray_tune.py")))


if __name__ == "__main__":
    unittest.main()
