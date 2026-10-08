import csv
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workload import build_scenario, describe

class WorkloadTests(unittest.TestCase):
    def setUp(self):
        self.env = {"AI_ENDPOINT": "https://example.invalid/v1", "AI_MODEL": "test", "TOKENIZER": "test"}

    def test_correlated_exact_mix_and_secret_free_scenario(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(self.env, AI_API_KEY="SECRET")
            scenario = build_scenario(env, Path(temp))
            with (Path(temp)/"workload.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([sum(r["bucket"] == str(b) for r in rows) for b in range(1,6)], [30,30,60,70,10])
            for row in rows:
                bucket = describe(env)["bins"][int(row["bucket"])-1]
                self.assertEqual(int(row["input_length"]), bucket["prompt_tokens"])
                self.assertEqual(int(row["output_length"]), bucket["output_tokens"])
            self.assertNotIn("SECRET", str(scenario))
            self.assertEqual(scenario["spec"]["profile"]["streams"], [12,24])
            self.assertTrue(scenario["spec"]["backend"]["verify"])

    def test_rejects_context_overflow_and_unrepresentable_mix(self):
        for override in ({"CONTEXT_TOKENS":"8192"}, {"REQUESTS_PER_STAGE":"12"}, {"MIX_WEIGHTS":"15,15,30,35,6"}):
            with self.assertRaises(ValueError): describe(dict(self.env, **override))

    def test_trace_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            build_scenario(self.env,p)
            first = (p/"workload.csv").read_bytes()
            build_scenario(self.env,p)
            self.assertEqual(first, (p/"workload.csv").read_bytes())

if __name__ == "__main__": unittest.main()
