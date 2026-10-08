"""Offline state-transition tests: no live Ray or inference traffic."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ray_control as control
from mutate_config import mutate


def fixture():
    source = {"applications": [
        {"name": "llm", "import_path": "server:app", "args": {"engine": {"max_num_seqs": 6}},
         "deployments": [{"name": "model", "num_replicas": 1}]},
        {"name": "other", "import_path": "other:app"}], "logging_config": {"log_level": "INFO"}}
    candidate = mutate(source, {"/applications/0/args/engine/max_num_seqs": 12}, "llm")
    return source, candidate


def state(config):
    return {"applications": {a["name"]: {"deployed_app_config": copy.deepcopy(a),
            "status": "RUNNING", "deployments": {"model": {
                "status": "HEALTHY", "target_num_replicas": 1,
                "replicas": [{"state": "RUNNING"}], "deployment_config": {"num_replicas": 1}}}}
            for a in config["applications"]}}


class API:
    def __init__(self, states):
        self.states = iter(states)
        self.puts = []

    def request(self, method="GET", payload=None):
        if method == "PUT":
            self.puts.append(payload)
        else:
            return next(self.states)


class ControlTests(unittest.TestCase):
    def test_mutation_preserves_source_and_unrelated_apps(self):
        source, candidate = fixture()
        self.assertEqual(source["applications"][0]["args"]["engine"]["max_num_seqs"], 6)
        self.assertEqual(candidate["applications"][0]["args"]["engine"]["max_num_seqs"], 12)
        self.assertEqual(source["applications"][1], candidate["applications"][1])

    def test_rejects_missing_pointer_wrong_scope_and_identity(self):
        source, _ = fixture()
        for pointer in ("/applications/0/args/engine/missing", "/applications/1/args/x",
                        "/applications/0/deployments/0/name", "/applications/0/args/a~2b"):
            with self.subTest(pointer=pointer), self.assertRaises(control.Error):
                mutate(source, {pointer: "changed"}, "llm")

    def test_preserves_globals_and_routes(self):
        source, candidate = fixture()
        for target in ("global", "route", "other"):
            bad = copy.deepcopy(candidate)
            if target == "global":
                bad["logging_config"]["log_level"] = "DEBUG"
            elif target == "route":
                bad["applications"][0]["route_prefix"] = "/changed"
            else:
                bad["applications"][1]["import_path"] = "new:app"
            with self.assertRaises(control.Error):
                control.validate_candidate(source, bad, "llm")

    def make_plan(self, directory):
        source, candidate = fixture()
        path = Path(directory) / "plan.json"
        control.ray.private_json(path, {"version": 1, "app": "llm", "endpoint": "http://ray",
            "offline": False, "original": source, "candidate": candidate,
            "snapshot": control.ray.configuration_snapshot(state(source))})
        return path, source, candidate

    def args(self, path, directory, action="apply"):
        return SimpleNamespace(action=action, plan=str(path), output=str(Path(directory) / action),
                               timeout=10, state_file=None)

    def test_apply_uses_saved_candidate_and_rollback_restores_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path, source, candidate = self.make_plan(directory)
            api = API([state(source), state(source), state(candidate)])
            control.run(self.args(path, directory), {"RAY_DASHBOARD_URL": "http://ray"}, api)
            self.assertEqual(api.puts, [candidate])
            api = API([state(candidate), state(candidate), state(source)])
            control.run(self.args(path, directory, "rollback"), {"RAY_DASHBOARD_URL": "http://ray"}, api)
            self.assertEqual(api.puts, [source])
            self.assertEqual((Path(directory) / "apply/submitted.json").stat().st_mode & 0o777, 0o600)

    def test_concurrent_change_blocks_apply_and_rollback(self):
        for action in ("apply", "rollback"):
            with tempfile.TemporaryDirectory() as directory:
                path, source, candidate = self.make_plan(directory)
                expected = source if action == "apply" else candidate
                changed = state(expected)
                changed["applications"]["other"]["deployed_app_config"]["route_prefix"] = "/new"
                api = API([state(expected), changed])
                with self.assertRaises(control.Error):
                    control.run(self.args(path, directory, action), {"RAY_DASHBOARD_URL": "http://ray"}, api)
                self.assertEqual(api.puts, [])

    def test_offline_or_wrong_endpoint_plan_cannot_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, _ = self.make_plan(directory)
            api = API([])
            with self.assertRaises(control.Error):
                control.run(self.args(path, directory), {"RAY_DASHBOARD_URL": "http://elsewhere"}, api)
            plan = json.loads(path.read_text())
            plan["offline"] = True
            path.write_text(json.dumps(plan))
            with self.assertRaises(control.Error):
                control.run(self.args(path, directory), {"RAY_DASHBOARD_URL": "http://ray"}, api)
            self.assertEqual(api.puts, [])

    def test_readiness_waits_for_replica_count_and_fails_unhealthy(self):
        source, candidate = fixture()
        pending = state(candidate)
        pending["applications"]["llm"]["deployments"]["model"]["replicas"] = []
        with patch.object(control.time, "sleep") as sleep:
            control.wait_app(API([pending, state(candidate)]), candidate, "llm", 10)
            sleep.assert_called_once()
        pending["applications"]["llm"]["status"] = "DEPLOY_FAILED"
        with self.assertRaises(control.Error):
            control.wait_app(API([pending]), candidate, "llm", 10)

    def test_external_scaler_prevents_replica_changes(self):
        source, candidate = fixture()
        source["applications"][0]["external_scaler_enabled"] = True
        candidate["applications"][0]["external_scaler_enabled"] = True
        candidate["applications"][0]["deployments"][0]["num_replicas"] = 2
        with self.assertRaises(control.Error):
            control.validate_candidate(source, candidate, "llm")

    def test_live_external_scaler_also_blocks_replica_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path, source, candidate = self.make_plan(directory)
            candidate["applications"][0]["deployments"][0]["num_replicas"] = 2
            plan = json.loads(path.read_text())
            plan["candidate"] = candidate
            path.write_text(json.dumps(plan))
            live = state(source)
            live["applications"]["llm"]["external_scaler_enabled"] = True
            api = API([live])
            with self.assertRaises(control.Error):
                control.run(self.args(path, directory), {"RAY_DASHBOARD_URL": "http://ray"}, api)
            self.assertEqual(api.puts, [])


if __name__ == "__main__":
    unittest.main()
