import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/collect_metrics.py"
spec = importlib.util.spec_from_file_location("collector", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class API:
    def request(self):
        return {"applications": {}, "private": "runtime-secret"}


class CollectionTests(unittest.TestCase):
    def test_query_encoding_and_endpoint_validation(self):
        expression = 'rate(custom_tokens{app="x+y"}[1m])'
        url = collector.query_url("https://metrics.example/proxy", expression, 100, 200, 15)
        self.assertEqual(parse_qs(urlsplit(url).query)["query"], [expression])
        self.assertEqual(urlsplit(url).path, "/proxy/api/v1/query_range")
        for base in ("ftp://bad", "https://user:secret@metrics", "https://metrics?token=secret"):
            with self.assertRaises(ValueError):
                collector.query_url(base, expression, 100, 200, 15)

    def test_empty_partial_and_nonfinite_are_not_zero(self):
        response = {"status": "success", "data": {"resultType": "matrix", "result": []}}
        self.assertEqual(collector.availability(response), "UNAVAILABLE")
        response["data"]["result"] = [{"metric": {"app": "llm"}, "values": [[100, "1"]]}]
        self.assertEqual(collector.availability(response), "AVAILABLE")
        response["data"]["result"][0]["values"][0][1] = "NaN"
        self.assertEqual(collector.availability(response), "PARTIAL")
        response["data"]["result"] = [None]
        self.assertEqual(collector.availability(response), "ERROR")

    def test_timestamp_requires_timezone_and_finite_number(self):
        self.assertEqual(collector.timestamp("1970-01-01T00:01:40Z"), 100)
        for value in ("NaN", "-1", "2026-10-08T12:00:00"):
            with self.assertRaises(ValueError):
                collector.timestamp(value)

    def test_raw_artifacts_private_and_failed_query_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queries = root / "queries.json"
            queries.write_text(json.dumps({"tokens": "operator_query", "missing": "unknown_query"}))
            args = SimpleNamespace(queries=str(queries), start="100", end="200", step=15,
                                   output=str(root / "out"))
            calls = []
            def fetch(url, token):
                calls.append((url, token))
                if "unknown_query" in url:
                    raise OSError("remote-secret")
                return {"status": "success", "data": {"resultType": "matrix", "result": []}}
            manifest = collector.collect(args, {"PROMETHEUS_URL": "https://metrics", "PROMETHEUS_AUTH_TOKEN": "secret"}, API(), fetch)
            self.assertEqual(manifest["metrics"]["tokens"]["status"], "UNAVAILABLE")
            self.assertEqual(manifest["metrics"]["missing"]["status"], "ERROR")
            self.assertEqual(manifest["window_validity"], "UNKNOWN")
            self.assertNotIn("secret", (root / "out/collection.json").read_text())
            self.assertEqual((root / "out/ray-state.json").stat().st_mode & 0o777, 0o600)
            self.assertTrue(all(token == "secret" for _, token in calls))
            with self.assertRaises(FileExistsError):
                collector.collect(args, {"PROMETHEUS_URL": "https://metrics"}, API(), fetch)

    def test_invalid_window_rejected_before_network(self):
        args = SimpleNamespace(queries=None, start="200", end="100", step=15, output="unused")
        with self.assertRaises(ValueError):
            collector.collect(args, {}, API())


if __name__ == "__main__":
    unittest.main()
