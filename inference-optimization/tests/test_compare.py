import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/compare_runs.py"
spec = importlib.util.spec_from_file_location("comparison", SCRIPT)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def write_run(folder, tps=(100, 100), validity="VALID"):
    folder.mkdir()
    context = {"profile_id": "mixed", "model_revision": "model-v1", "tokenizer_revision": "tok-v1",
               "serving_image": "image-digest", "ray_version": "fixture", "engine_version": "fixture",
               "hardware": "fixture", "cache_policy": "fixed", "generation_settings": {},
               "measurement_policy": {"warmup_seconds": 15}, "required_gates": ["p95_ttft_ms"],
               "quality_kind": "synthetic_correctness_smoke"}
    stages = []
    for index, value in enumerate(tps):
        gates = {key: {"status": "PASS"} for key in ("metric_integrity", "error_rate", "completed_requests")}
        gates["p95_ttft_ms"] = {"status": "PASS", "threshold": 100, "comparison": "<="}
        stages.append({"index": index, "status": "PASS", "errors": [], "gates": gates,
                       "metrics": {"output_tps": value, "p95_ttft_ms": 80, "p95_itl_ms": 10,
                                   "p95_e2e_ms": 1000, "error_rate": 0, "completed_requests": 200}})
    files = {"manifest.json": {"streams": [12, 24], "seed": 42}, "experiment-context.json": context,
             "status.json": {"status": "PASS", "live_benchmark_run": True},
             "quality.json": {"status": "PASS", "kind": "synthetic_correctness_smoke"},
             "observation.json": {"window_validity": validity},
             "evaluation.json": {"status": "PASS", "benchmarks": stages}}
    for name, value in files.items():
        (folder / name).write_text(json.dumps(value))
    return folder


class ComparisonTests(unittest.TestCase):
    def test_improvement_needs_no_regressing_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = write_run(root / "before")
            after = write_run(root / "after", (110, 105))
            self.assertEqual(comparison.compare([before], [after])["decision"], "ACCEPTABLE_FOR_CONFIRMATION")
            regressed = write_run(root / "regressed", (130, 90))
            self.assertEqual(comparison.compare([before], [regressed])["decision"], "REJECT")
            plateau = write_run(root / "plateau", (101, 100))
            self.assertEqual(comparison.compare([before], [plateau])["decision"], "REJECT")

    def test_unknown_or_invalid_window_is_inconclusive(self):
        for validity in ("UNKNOWN", "INVALID"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                before = write_run(root / "before")
                after = write_run(root / "after", (110, 110), validity)
                self.assertEqual(comparison.compare([before], [after])["decision"], "INCONCLUSIVE")

    def test_changed_profile_context_or_required_gate_fails_closed(self):
        for target in ("manifest", "context", "gate", "quality", "mock", "nonfinite"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                before = write_run(root / "before")
                after = write_run(root / "after", (110, 110))
                filename = {"manifest": "manifest.json", "context": "experiment-context.json", "gate": "evaluation.json",
                            "quality": "quality.json", "mock": "status.json", "nonfinite": "evaluation.json"}[target]
                data = json.loads((after / filename).read_text())
                if target == "manifest":
                    data["seed"] = 43
                elif target == "context":
                    data["hardware"] = "different"
                elif target == "gate":
                    data["benchmarks"][0]["gates"]["p95_ttft_ms"]["status"] = "NOT_CONFIGURED"
                elif target == "quality":
                    data["status"] = "FAIL"
                elif target == "mock":
                    data["live_benchmark_run"] = False
                else:
                    data["benchmarks"][0]["metrics"]["p95_ttft_ms"] = float("nan")
                (after / filename).write_text(json.dumps(data))
                self.assertEqual(comparison.compare([before], [after])["decision"], "INCONCLUSIVE")

    def test_missing_profile_and_invalid_thresholds_are_rejected(self):
        for value in (0, float("nan"), True, -1):
            with self.assertRaises(ValueError):
                comparison.compare(["x"], ["y"], value)
        with self.assertRaises(ValueError):
            comparison.compare(["x"], [])


if __name__ == "__main__":
    unittest.main()
