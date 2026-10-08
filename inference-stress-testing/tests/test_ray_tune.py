"""Safety and state-transition checks for full-config Ray Serve updates."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ray_tune.py"
SPEC = importlib.util.spec_from_file_location("ray_tune", SCRIPT)
ray = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ray)


def fixtures():
    source = {"logging_config": {"log_level": "WARNING"}, "applications": [
        {"name": "llm", "import_path": "server:app", "route_prefix": "/", "deployments": [
            {"name": "model", "num_replicas": "auto", "autoscaling_config": {"min_replicas": 1, "max_replicas": 4}}]},
        {"name": "other", "import_path": "other:app", "route_prefix": "/other"}]}
    state = {"applications": {app["name"]: {
        "deployed_app_config": copy.deepcopy(app), "status": "RUNNING", "deployments": {}}
        for app in source["applications"]}}
    state["applications"]["llm"]["deployments"]["model"] = {
        "status": "HEALTHY", "target_num_replicas": 1,
        "replicas": [{"state": "RUNNING"}], "deployment_config": {
            "num_replicas": "auto", "ray_actor_options": {
                "num_cpus": 1, "num_gpus": 1, "resources": {"special": 1},
                "runtime_env": {"env_vars": {"PRIVATE_KEY": "do-not-print"}}}}}
    return source, state


class FakeAPI:
    def __init__(self, states):
        self.states = iter(states)
        self.puts = []

    def request(self, method="GET", payload=None):
        if method == "PUT":
            self.puts.append(copy.deepcopy(payload))
            return None
        return next(self.states)


class RayTuneTests(unittest.TestCase):
    def test_preserves_other_apps_globals_and_effective_actor_options(self):
        source, state = fixtures()
        proposed = ray.build_proposal(source, state, "llm", "model", {
            "num_replicas": 2, "ray_actor_options": {"num_cpus": 4}})
        deployment = proposed["applications"][0]["deployments"][0]
        self.assertEqual(deployment["num_replicas"], 2)
        self.assertIsNone(deployment["autoscaling_config"])
        self.assertEqual(deployment["ray_actor_options"]["num_gpus"], 1)
        self.assertEqual(deployment["ray_actor_options"]["resources"], {"special": 1})
        self.assertEqual(proposed["applications"][1], source["applications"][1])
        self.assertEqual(proposed["logging_config"], source["logging_config"])
        self.assertEqual(source["applications"][0]["deployments"][0]["num_replicas"], "auto")

    def test_omitted_python_defined_deployment_can_be_overridden(self):
        source, state = fixtures()
        source["applications"][0].pop("deployments")
        state["applications"]["llm"]["deployed_app_config"] = copy.deepcopy(source["applications"][0])
        result = ray.build_proposal(source, state, "llm", "model", {"max_ongoing_requests": 24})
        self.assertEqual(result["applications"][0]["deployments"], [{"name": "model", "max_ongoing_requests": 24}])

    def test_rejects_omitted_apps_stale_source_and_missing_live_config(self):
        for change in ("omitted", "stale", "missing"):
            with self.subTest(change=change):
                source, state = fixtures()
                if change == "omitted":
                    source["applications"].pop()
                elif change == "stale":
                    source["applications"][0]["route_prefix"] = "/stale"
                else:
                    state["applications"]["other"]["deployed_app_config"] = None
                with self.assertRaises(ray.TuningError):
                    ray.build_proposal(source, state, "llm", "model", {"num_replicas": 2})

    def test_rejects_static_replica_tuning_under_external_scaler(self):
        source, state = fixtures()
        state["applications"]["llm"]["external_scaler_enabled"] = True
        with self.assertRaises(ray.TuningError):
            ray.build_proposal(source, state, "llm", "model", {"num_replicas": 2})

    def test_rejects_bad_numeric_overrides_without_echoing_value(self):
        for value in ("nan", "inf", "-1", "not-a-number-secret"):
            with self.subTest(value=value), self.assertRaises(ray.TuningError) as error:
                ray.overrides_from_env({"RAY_NUM_CPUS": value})
            self.assertNotIn(value, str(error.exception))

    def test_readiness_waits_for_desired_config_and_replica_count(self):
        source, old = fixtures()
        proposal = ray.build_proposal(source, old, "llm", "model", {"num_replicas": 2})
        partial = copy.deepcopy(old)
        partial["applications"]["llm"]["deployed_app_config"] = proposal["applications"][0]
        partial["applications"]["llm"]["deployments"]["model"]["target_num_replicas"] = 2
        ready = copy.deepcopy(partial)
        ready["applications"]["llm"]["deployments"]["model"]["replicas"].append({"state": "RUNNING"})
        applied = copy.deepcopy(ready)
        applied["applications"]["llm"]["deployments"]["model"]["deployment_config"]["num_replicas"] = 2
        api = FakeAPI([old, partial, ready, applied])
        with patch.object(ray.time, "sleep") as sleep:
            ray.wait_ready(api, proposal, "llm", "model", 10)
        self.assertEqual(sleep.call_count, 3)

    def test_failed_deployment_does_not_echo_remote_secret_message(self):
        source, state = fixtures()
        state["applications"]["llm"]["status"] = "DEPLOY_FAILED"
        state["applications"]["llm"]["message"] = "PRIVATE_KEY=do-not-print"
        with self.assertRaises(ray.TuningError) as error:
            ray.wait_ready(FakeAPI([state]), source, "llm", "model", 10)
        self.assertNotIn("do-not-print", str(error.exception))

    def test_changed_config_prevents_put_and_snapshots_are_private(self):
        source, initial = fixtures()
        changed = copy.deepcopy(initial)
        changed["applications"]["other"]["deployed_app_config"]["route_prefix"] = "/new"
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "serve.json"
            source_path.write_text(json.dumps(source))
            output = Path(directory) / "snapshots"
            env = {"RAY_SERVE_CONFIG": str(source_path), "RAY_APP_NAME": "llm",
                   "RAY_DEPLOYMENT_NAME": "model", "RAY_NUM_REPLICAS": "2"}
            api = FakeAPI([initial, changed])
            args = SimpleNamespace(action="apply", state_file=None, output=str(output))
            with self.assertRaises(ray.TuningError):
                ray.run(args, env, api)
            self.assertEqual(api.puts, [])
            for name in ("original.json", "proposed.json"):
                self.assertEqual(os.stat(output / name).st_mode & 0o777, 0o600)

    def test_apply_puts_only_after_second_get_then_waits(self):
        source, initial = fixtures()
        proposed = ray.build_proposal(source, initial, "llm", "model", {"num_replicas": 2})
        ready = copy.deepcopy(initial)
        ready["applications"]["llm"]["deployed_app_config"] = proposed["applications"][0]
        model = ready["applications"]["llm"]["deployments"]["model"]
        model["target_num_replicas"] = 2
        model["deployment_config"]["num_replicas"] = 2
        model["replicas"] = [{"state": "RUNNING"}, {"state": "RUNNING"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serve.json"
            path.write_text(json.dumps(source))
            args = SimpleNamespace(action="apply", state_file=None, output=str(Path(directory) / "result"))
            env = {"RAY_SERVE_CONFIG": str(path), "RAY_APP_NAME": "llm",
                   "RAY_DEPLOYMENT_NAME": "model", "RAY_NUM_REPLICAS": "2"}
            api = FakeAPI([initial, initial, ready])
            with patch("builtins.print"):
                ray.run(args, env, api)
            self.assertEqual(api.puts, [proposed])

    def test_offline_state_cannot_apply(self):
        with self.assertRaises(ray.TuningError):
            ray.run(SimpleNamespace(action="apply", state_file="state.json"), {})

    def test_snapshot_refuses_to_overwrite_or_follow_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_text("keep me")
            link = Path(directory) / "proposed.json"
            link.symlink_to(target)
            with self.assertRaises(ray.TuningError):
                ray.private_json(link, {"secret": "hidden"})
            self.assertEqual(target.read_text(), "keep me")


if __name__ == "__main__":
    unittest.main()
