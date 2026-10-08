#!/usr/bin/env python3
"""Native Python status/plan/apply/rollback for operator-owned Ray Serve configs.

Uses the companion skill's tested REST transport and full-config verification.
Ray has no conditional PUT; one configuration writer is still required.
"""
import argparse
import copy
import importlib.util
import math
import os
from pathlib import Path
import sys
import time

SHARED = Path(__file__).resolve().parents[2] / "inference-stress-testing/scripts/ray_tune.py"
if not SHARED.is_file():
    raise SystemExit("Install inference-stress-testing alongside ray-autotune-inference.")
spec = importlib.util.spec_from_file_location("shared_ray", SHARED)
ray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ray)
Error = ray.TuningError


def validate_candidate(source, candidate, app_name):
    before, after = ray.applications(source), ray.applications(candidate)
    if app_name not in before or set(before) != set(after):
        raise Error("Candidate must preserve the complete application set.")
    if {k: v for k, v in source.items() if k != "applications"} != {
            k: v for k, v in candidate.items() if k != "applications"}:
        raise Error("Candidate must preserve global Serve settings.")
    for name in before:
        if name != app_name and ray.normalized_app(before[name]) != ray.normalized_app(after[name]):
            raise Error("Candidate changes an unrelated application.")
    for key in ("name", "import_path", "route_prefix", "runtime_env", "external_scaler_enabled"):
        if before[app_name].get(key) != after[app_name].get(key):
            raise Error("Candidate changes application identity, route, runtime, or scaling ownership.")
    def deployment_names(app):
        names = [d["name"] for d in app.get("deployments", [])]
        if len(set(names)) != len(names):
            raise Error("Duplicate deployment names in configuration.")
        return set(names)
    if deployment_names(before[app_name]) != deployment_names(after[app_name]):
        raise Error("Candidate must preserve deployment identities.")
    if source == candidate:
        raise Error("Candidate contains no change.")
    if before[app_name].get("external_scaler_enabled"):
        def scaling(app):
            return {d["name"]: (d.get("num_replicas"), d.get("autoscaling_config"))
                    for d in app.get("deployments", [])}
        if scaling(before[app_name]) != scaling(after[app_name]):
            raise Error("An external scaler owns replica settings.")


def wait_app(api, config, app_name, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = api.request()
        app = state.get("applications", {}).get(app_name, {})
        deps = app.get("deployments", {})
        if app.get("status") in ("DEPLOY_FAILED", "UNHEALTHY", "DELETING") or any(
                d.get("status") == "UNHEALTHY" for d in deps.values()):
            raise Error("Application failed or became unhealthy; inspect diagnostics or roll back.")
        try:
            ray.verify_source(config, state)
            ready = app.get("status") == "RUNNING" and bool(deps)
            for dep in deps.values():
                target = dep.get("target_num_replicas")
                replicas = dep.get("replicas", [])
                ready &= (dep.get("status") == "HEALTHY" and type(target) is int and target > 0
                          and len(replicas) == target
                          and all(r.get("state") == "RUNNING" for r in replicas))
            for desired in ray.applications(config)[app_name].get("deployments", []):
                effective = deps.get(desired["name"], {}).get("deployment_config", {})
                for key in ("num_replicas", "max_ongoing_requests", "autoscaling_config", "ray_actor_options"):
                    if key not in desired:
                        continue
                    value = desired[key]
                    actual = effective.get(key)
                    if isinstance(value, dict) and isinstance(actual, dict):
                        ready &= all(actual.get(k) == v for k, v in value.items())
                    else:
                        ready &= actual == value
            if ready:
                return state
        except Error:
            pass  # Submitted config can lag the PUT during reconciliation.
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise Error("Readiness timed out; no automatic rollback was attempted.")


def run(args, env, api=None):
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise Error("Timeout must be finite and positive.")
    if args.action != "plan" and args.state_file:
        raise Error("Recorded state is only accepted for offline plan.")
    endpoint = env.get("RAY_DASHBOARD_URL", "")
    if not args.state_file and api is None:
        api = ray.RayAPI(endpoint, env.get("RAY_AUTH_TOKEN", ""),
                         env.get("CERT_FILE") or env.get("SSL_CERT_FILE", ""))
    if args.action == "status":
        state = api.request()
        # Full state can contain secrets: save privately, never dump to stdout.
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        ray.private_json(output / "state.json", state)
        print("Ray state saved privately; no deployment changes.")
        return
    if args.action == "plan":
        if not args.source or not args.candidate or not args.app:
            raise Error("Plan requires --source, --candidate, and --app.")
        source, candidate = ray.load_json(args.source), ray.load_json(args.candidate)
        validate_candidate(source, candidate, args.app)
        state = ray.load_json(args.state_file) if args.state_file else api.request()
        ray.verify_source(source, state)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        ray.private_json(output / "plan.json", {"version": 1, "app": args.app,
                         "endpoint": endpoint, "offline": bool(args.state_file),
                         "original": source, "candidate": candidate,
                         "snapshot": ray.configuration_snapshot(state)})
        print("Private plan saved; no deployment changes.")
        return
    if not args.plan:
        raise Error("Apply and rollback require --plan.")
    plan = ray.load_json(args.plan)
    if plan.get("version") != 1 or plan.get("offline") or plan.get("endpoint") != endpoint:
        raise Error("Use a live plan for this dashboard URL; refresh the plan.")
    source, candidate, app_name = plan["original"], plan["candidate"], plan["app"]
    validate_candidate(source, candidate, app_name)
    expected, desired = (source, candidate) if args.action == "apply" else (candidate, source)
    state = api.request()
    ray.verify_source(expected, state)
    if state["applications"][app_name].get("external_scaler_enabled"):
        guarded = copy.deepcopy(expected)
        guarded["applications"] = [dict(a, external_scaler_enabled=True) if a["name"] == app_name else a
                                   for a in guarded["applications"]]
        guarded_desired = copy.deepcopy(desired)
        guarded_desired["applications"] = [dict(a, external_scaler_enabled=True) if a["name"] == app_name else a
                                           for a in guarded_desired["applications"]]
        validate_candidate(guarded, guarded_desired, app_name)
    if args.action == "apply" and ray.configuration_snapshot(state) != plan["snapshot"]:
        raise Error("Live configuration changed since planning; refresh the plan.")
    latest = api.request()
    if ray.configuration_snapshot(state) != ray.configuration_snapshot(latest):
        raise Error("Configuration changed before PUT; no change submitted.")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    ray.private_json(output / "before.json", state)
    ray.private_json(output / "submitted.json", desired)
    api.request("PUT", desired)
    final = wait_app(api, desired, app_name, args.timeout)
    ray.private_json(output / "ready.json", final)
    print("Application ready; verify engine settings and probe the endpoint before load testing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "plan", "apply", "rollback"))
    parser.add_argument("--source", help="Complete authoritative Serve JSON")
    parser.add_argument("--candidate", help="Reviewed complete candidate Serve JSON")
    parser.add_argument("--app", help="Application being tuned")
    parser.add_argument("--plan", help="Private plan.json from a live plan")
    parser.add_argument("--state-file", help="Recorded GET response, offline plan only")
    parser.add_argument("--output", required=True, help="Fresh private artifact directory")
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    try:
        run(args, ray.config.trusted_environment(ray.config.load_environment()))
    except Error as exc:
        print(f"Ray operation failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        # Input configs and remote messages may contain credentials.
        print("Ray operation failed; check inputs, live state, ownership, and private artifacts.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
