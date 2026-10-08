#!/usr/bin/env python3
"""Plan or apply narrowly scoped Ray Serve overrides using its full-config REST API.

Source JSON must match every live application's submitted config. Global settings
not exposed by GET can only be preserved from this operator-maintained source.
Ray has no compare-and-swap PUT: use one configuration writer during an apply.
"""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class TuningError(Exception):
    """An actionable failure whose message contains no remote response or secret."""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise TuningError("Cannot read a required JSON file.") from exc


def private_json(path, value):
    """Never follow an existing output symlink; protect snapshots containing envs."""
    data = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    except OSError as exc:
        raise TuningError("Cannot create snapshot; choose a new --output directory.") from exc


def applications(config):
    apps = config.get("applications") if isinstance(config, dict) else None
    if not isinstance(apps, list) or not apps:
        raise TuningError("Source config must contain a nonempty applications array.")
    indexed = {}
    for app in apps:
        name = app.get("name") if isinstance(app, dict) else None
        if not isinstance(name, str) or not name or name in indexed:
            raise TuningError("Every source application needs a unique explicit name.")
        indexed[name] = app
    return indexed


def normalized_app(app):
    result = copy.deepcopy(app)
    if isinstance(result.get("deployments"), list):
        if not all(isinstance(item, dict) for item in result["deployments"]):
            raise TuningError("Source deployments must contain objects.")
        result["deployments"].sort(key=lambda item: item.get("name", ""))
    return result


def verify_source(config, state):
    expected = applications(config)
    live = state.get("applications") if isinstance(state, dict) else None
    if not isinstance(live, dict) or set(expected) != set(live):
        raise TuningError("Source and live application sets differ; refresh the full config.")
    for name, app in expected.items():
        submitted = live[name].get("deployed_app_config")
        if not isinstance(submitted, dict) or not submitted.get("import_path"):
            raise TuningError("A live application has no recoverable submitted config.")
        if normalized_app(app) != normalized_app(submitted):
            raise TuningError("Source application config is stale; refresh the full config.")
    # Other global settings, including logging_config, are not exposed by GET.
    for key in ("proxy_location", "http_options", "grpc_options", "target_capacity"):
        if key in config and key in state and state[key] is not None:
            desired, current = config[key], state[key]
            if isinstance(desired, dict) and isinstance(current, dict):
                equal = all(current.get(k) == v for k, v in desired.items())
            else:
                equal = desired == current
            if not equal:
                raise TuningError("Source global settings differ from the live cluster.")


def numeric_env(env, key, integer=False, positive=False):
    value = env.get(key, "").strip()
    if not value:
        return None
    try:
        result = int(value) if integer else float(value)
        if not math.isfinite(result) or (result <= 0 if positive else result < 0):
            raise ValueError()
    except (ValueError, OverflowError) as exc:
        raise TuningError(f"{key} must be a finite {'positive' if positive else 'nonnegative'} number.") from exc
    return result


def overrides_from_env(env):
    overrides = {}
    for key, variable in (("num_replicas", "RAY_NUM_REPLICAS"),
                          ("max_ongoing_requests", "RAY_MAX_ONGOING_REQUESTS")):
        value = numeric_env(env, variable, integer=True, positive=True)
        if value is not None:
            overrides[key] = value
    actors = {}
    for key, variable in (("num_cpus", "RAY_NUM_CPUS"), ("num_gpus", "RAY_NUM_GPUS")):
        value = numeric_env(env, variable)
        if value is not None:
            actors[key] = value
    if actors:
        overrides["ray_actor_options"] = actors
    if not overrides:
        raise TuningError("Set at least one RAY_NUM_REPLICAS, RAY_MAX_ONGOING_REQUESTS, RAY_NUM_CPUS, or RAY_NUM_GPUS override.")
    return overrides


def build_proposal(source, state, app_name, deployment_name, overrides):
    verify_source(source, state)
    proposal = copy.deepcopy(source)
    app = applications(proposal).get(app_name)
    live_app = state["applications"].get(app_name)
    if app is None or live_app is None:
        raise TuningError("The named Ray application does not exist.")
    live_deployment = live_app.get("deployments", {}).get(deployment_name)
    if not isinstance(live_deployment, dict):
        raise TuningError("The named Ray deployment does not exist.")
    if "num_replicas" in overrides and (app.get("external_scaler_enabled") or live_app.get("external_scaler_enabled")):
        raise TuningError("An external scaler owns replica counts; use its scaling API.")
    deployments = app.setdefault("deployments", [])
    if not isinstance(deployments, list):
        raise TuningError("Source deployments must be an array.")
    matches = [item for item in deployments if item.get("name") == deployment_name]
    if len(matches) > 1:
        raise TuningError("Source contains duplicate target deployments.")
    deployment = matches[0] if matches else {"name": deployment_name}
    if not matches:
        deployments.append(deployment)
    patch = copy.deepcopy(overrides)
    if "ray_actor_options" in patch:
        effective = live_deployment.get("deployment_config", {}).get("ray_actor_options")
        if not isinstance(effective, dict):
            raise TuningError("Cannot preserve actor options: effective deployment config is unavailable.")
        merged = copy.deepcopy(effective)
        merged.update(patch["ray_actor_options"])
        patch["ray_actor_options"] = merged
    if "num_replicas" in patch:
        patch["autoscaling_config"] = None
    deployment.update(patch)
    return proposal


def configuration_snapshot(state):
    """Exclude health/replica status changes, which are expected during operation."""
    return {
        "global": {key: state.get(key) for key in
                   ("proxy_location", "http_options", "grpc_options", "target_capacity")},
        "applications": {
            name: {"submitted": app.get("deployed_app_config"),
                   "effective": {dep: details.get("deployment_config") for dep, details
                                 in app.get("deployments", {}).items()}}
            for name, app in state.get("applications", {}).items()
        },
    }


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Never forward dashboard authorization to a redirected host.


class RayAPI:
    def __init__(self, endpoint, token=""):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise TuningError("RAY_DASHBOARD_URL must be an HTTP(S) base URL without credentials, query, or fragment.")
        self.url = endpoint.rstrip("/") + "/api/serve/applications/"
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self.opener = urllib.request.build_opener(NoRedirects())
        if token:
            self.headers["Authorization"] = "Bearer " + token

    def request(self, method="GET", payload=None):
        body = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        request = urllib.request.Request(self.url, body, self.headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            raise TuningError(f"Ray dashboard returned HTTP {exc.code}; inspect cluster logs.") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise TuningError("Cannot reach the Ray dashboard with the supplied URL and credentials.") from None
        if method == "PUT":
            return None
        try:
            result = json.loads(data)
        except ValueError as exc:
            raise TuningError("Ray dashboard did not return valid JSON.") from exc
        if not isinstance(result, dict):
            raise TuningError("Unexpected Ray dashboard response shape.")
        return result


def wait_ready(api, proposal, app_name, deployment_name, timeout):
    deadline = time.monotonic() + timeout
    desired = next(item for item in applications(proposal)[app_name]["deployments"]
                   if item["name"] == deployment_name)
    while time.monotonic() < deadline:
        state = api.request()
        try:
            verify_source(proposal, state)
        except TuningError:
            time.sleep(min(2, max(0, deadline - time.monotonic())))
            continue
        app = state["applications"][app_name]
        deployment = app.get("deployments", {}).get(deployment_name, {})
        if app.get("status") in ("DEPLOY_FAILED", "UNHEALTHY", "DELETING") or deployment.get("status") == "UNHEALTHY":
            raise TuningError("Ray deployment failed or became unhealthy; inspect cluster diagnostics.")
        replicas = deployment.get("replicas", [])
        effective = deployment.get("deployment_config", {})
        checks = {key: desired[key] for key in ("max_ongoing_requests", "ray_actor_options")
                  if key in desired}
        if isinstance(desired.get("num_replicas"), int):
            checks["num_replicas"] = desired["num_replicas"]
        if "autoscaling_config" in desired and desired["autoscaling_config"] is None:
            checks["autoscaling_config"] = None
        settings_ready = all(effective.get(key) == value for key, value in checks.items())
        target = deployment.get("target_num_replicas")
        if target is None:
            target = deployment.get("deployment_config", {}).get("num_replicas")
            if state.get("target_capacity") not in (None, 100):
                target = None
        count_ready = isinstance(target, int) and len(replicas) == target
        if (app.get("status") == "RUNNING" and deployment.get("status") == "HEALTHY"
                and settings_ready and count_ready and all(r.get("state") == "RUNNING" for r in replicas)):
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise TuningError("Ray readiness timed out; inspect deployment state before benchmarking.")


def run(args, env, api=None):
    if args.action == "apply" and args.state_file:
        raise TuningError("--state-file is only supported for offline plan.")
    for key in ("RAY_SERVE_CONFIG", "RAY_APP_NAME", "RAY_DEPLOYMENT_NAME"):
        if not env.get(key):
            raise TuningError(f"Set {key}.")
    source = load_json(env["RAY_SERVE_CONFIG"])
    overrides = overrides_from_env(env)
    timeout = numeric_env(env, "RAY_READY_TIMEOUT_SECONDS", positive=True) or 900
    if not args.state_file and api is None:
        api = RayAPI(env.get("RAY_DASHBOARD_URL", ""), env.get("RAY_AUTH_TOKEN", ""))
    state = load_json(args.state_file) if args.state_file else api.request()
    proposal = build_proposal(source, state, env["RAY_APP_NAME"], env["RAY_DEPLOYMENT_NAME"], overrides)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    private_json(output / "original.json", source)
    private_json(output / "proposed.json", proposal)
    if args.action == "plan":
        print("Ray plan written; no deployment changes were made.")
        return
    latest = api.request()
    if configuration_snapshot(latest) != configuration_snapshot(state):
        raise TuningError("Ray configuration changed during planning; refresh the source and retry.")
    api.request("PUT", proposal)
    wait_ready(api, proposal, env["RAY_APP_NAME"], env["RAY_DEPLOYMENT_NAME"], timeout)
    print("Ray deployment is ready. Run an inference probe before benchmarking.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--output", default="artifacts/ray", help="Fresh directory for private original/proposed snapshots")
    parser.add_argument("--state-file", help="Recorded GET response for offline plan only")
    args = parser.parse_args()
    try:
        run(args, os.environ)
    except (TuningError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Ray tuning failed: {exc}" if isinstance(exc, TuningError)
              else "Ray tuning failed: invalid input or local filesystem error.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
