"""Meaningful fail-closed checks against GuideLLM 0.8 report paths and units."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"
spec = importlib.util.spec_from_file_location("evaluate", SCRIPT)
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


def report():
    def distribution(value):
        return {"successful": {"count": 100, "mean": value, "percentiles": {"p95": value}}}
    return {"metadata": {"version": 2, "guidellm_version": "0.8.0"}, "benchmarks": [{
        "metrics": {
            "request_totals": {"successful": 100, "errored": 0, "incomplete": 0, "total": 100},
            "time_to_first_token_ms": distribution(200),
            "inter_token_latency_ms": distribution(20),
            "request_latency": distribution(2),
            "output_tokens_per_second": distribution(500),
        },
        "requests": {"successful": []},
    }]}


class EvaluationTests(unittest.TestCase):
    def test_defaults_and_optional_gates(self):
        result = evaluate.evaluate_report(report(), {})
        self.assertEqual(result["status"], "PASS")
        gates = result["benchmarks"][0]["gates"]
        self.assertEqual(gates["p95_ttft_ms"]["status"], "NOT_CONFIGURED")
        self.assertEqual(gates["completed_requests"]["status"], "PASS")

    def test_e2e_seconds_to_ms_and_inclusive_threshold(self):
        passed = evaluate.evaluate_report(report(), {"EVAL_P95_E2E_MS": "2000"})
        self.assertEqual(passed["status"], "PASS")
        failed = evaluate.evaluate_report(report(), {"EVAL_P95_E2E_MS": "1999"})
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["benchmarks"][0]["metrics"]["p95_e2e_ms"], 2000)

    def test_incomplete_requests_count_against_error_budget(self):
        data = report()
        data["benchmarks"][0]["metrics"]["request_totals"].update(incomplete=1, total=101)
        self.assertEqual(evaluate.evaluate_report(data, {})["status"], "FAIL")
        self.assertEqual(evaluate.evaluate_report(data, {"EVAL_MAX_ERROR_RATE": "0.01"})["status"], "PASS")

    def test_no_requests_empty_reports_and_bad_counts_fail(self):
        for totals in (
            {"successful": 0, "errored": 0, "incomplete": 0, "total": 0},
            {"successful": 100, "errored": 0, "incomplete": 0, "total": 101},
            {"successful": 100, "errored": 0, "incomplete": 0, "total": True},
        ):
            data = report()
            data["benchmarks"][0]["metrics"]["request_totals"] = totals
            self.assertEqual(evaluate.evaluate_report(data, {})["status"], "FAIL")
        self.assertEqual(evaluate.evaluate_report({"metadata": report()["metadata"], "benchmarks": []}, {})["status"], "FAIL")

    def test_missing_empty_and_nonfinite_metrics_fail_closed(self):
        for value in (None, float("nan"), float("inf"), -1, "200"):
            with self.subTest(value=value):
                data = report()
                data["benchmarks"][0]["metrics"]["time_to_first_token_ms"]["successful"]["percentiles"]["p95"] = value
                result = evaluate.evaluate_report(data, {})
                self.assertEqual(result["status"], "FAIL")
                json.dumps(result, allow_nan=False)
        for replacement in ({}, {"successful": {"count": 0, "mean": 0, "percentiles": {"p95": 0}}}):
            data = report()
            data["benchmarks"][0]["metrics"]["inter_token_latency_ms"] = replacement
            self.assertEqual(evaluate.evaluate_report(data, {})["status"], "FAIL")

    def test_each_concurrency_must_pass(self):
        data = report()
        second = copy.deepcopy(data["benchmarks"][0])
        second["metrics"]["output_tokens_per_second"]["successful"]["mean"] = 10
        data["benchmarks"].append(second)
        result = evaluate.evaluate_report(data, {"EVAL_MIN_OUTPUT_TPS": "100"})
        self.assertEqual([b["status"] for b in result["benchmarks"]], ["PASS", "FAIL"])
        self.assertEqual(result["status"], "FAIL")

    def test_invalid_thresholds_and_unknown_schemas_fail(self):
        for env in ({"EVAL_MIN_COMPLETED_REQUESTS": "0"}, {"EVAL_MAX_ERROR_RATE": "15"},
                    {"EVAL_P95_ITL_MS": "nan"}, {"EVAL_P95_TTFT_MS": "bad"}):
            self.assertEqual(evaluate.evaluate_report(report(), env)["status"], "FAIL")
        data = report()
        data["metadata"]["version"] = 1
        self.assertEqual(evaluate.evaluate_report(data, {})["status"], "FAIL")

    def test_length_audit_distinguishes_caps_usage_and_estimates(self):
        data = report()
        def request(tokens, usage=True):
            return {"request_args": json.dumps({"body": {"max_tokens": 256}}),
                    "output_metrics": {"total_tokens": tokens if usage else None}, "output_tokens": tokens}
        data["benchmarks"][0]["requests"]["successful"] = [request(256), request(32), request(200, False)]
        audit = evaluate.evaluate_report(data, {})["benchmarks"][0]["output_length_audit"]
        group = audit["by_requested_output_cap"][0]
        self.assertEqual(group["requested_output_cap_tokens"], 256)
        self.assertEqual(group["at_cap_possible_truncation"], 1)
        self.assertEqual(group["below_cap"], 1)
        self.assertEqual(group["reported_output_tokens_mean"], 144)
        self.assertEqual(audit["samples_with_only_stream_iteration_estimates"], 1)

    def test_cli_persists_failure_and_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evaluation.json"
            markdown = Path(directory) / "summary.md"
            completed = subprocess.run([sys.executable, str(SCRIPT), str(Path(directory) / "missing.json"),
                                        "--output", str(output), "--markdown", str(markdown)],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(output.read_text())["status"], "FAIL")
            self.assertIn("FAIL", markdown.read_text())


if __name__ == "__main__":
    unittest.main()
