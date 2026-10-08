#!/usr/bin/env python3
"""Read-only Ray state snapshot and explicit Prometheus window queries."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SHARED = Path(__file__).resolve().parents[2] / "inference-stress-testing/scripts/ray_tune.py"
if not SHARED.is_file():
    raise SystemExit("Install the bundled inference-stress-testing skill alongside this skill.")
spec = importlib.util.spec_from_file_location("observed_ray", SHARED)
ray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ray)


def timestamp(value):
    try:
        result = float(value)
    except ValueError:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        result = date.timestamp()
    if not math.isfinite(result) or result < 0:
        raise ValueError("Timestamp must be finite and nonnegative")
    return result


def query_url(base, expression, start, end, step):
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("PROMETHEUS_URL must be a credential-free HTTP(S) base URL")
    return base.rstrip("/") + "/api/v1/query_range?" + urllib.parse.urlencode(
        {"query": expression, "start": start, "end": end, "step": step})


def fetch(url, token=""):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    opener = urllib.request.build_opener(ray.NoRedirects())
    request = urllib.request.Request(url, headers=headers, method="GET")
    with opener.open(request, timeout=30) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Metrics response exceeds collection limit")
    return json.loads(data)


def availability(response):
    if not isinstance(response, dict) or response.get("status") != "success":
        return "ERROR"
    data = response.get("data", {})
    if not isinstance(data, dict) or data.get("resultType") != "matrix" or not isinstance(data.get("result"), list):
        return "ERROR"
    series = data["result"]
    if any(not isinstance(s, dict) for s in series):
        return "ERROR"
    if not series or not any(s.get("values") or s.get("histograms") for s in series):
        return "UNAVAILABLE"
    if response.get("warnings") or response.get("infos"):
        return "PARTIAL"
    for s in series:
        if not s.get("values") or s.get("histograms"):
            return "PARTIAL"  # Retain native histograms without pretending float semantics.
        for sample in s["values"]:
            if not isinstance(sample, list) or len(sample) != 2:
                return "PARTIAL"
            try:
                if not all(math.isfinite(float(v)) for v in sample):
                    return "PARTIAL"
            except (TypeError, ValueError):
                return "PARTIAL"
    return "AVAILABLE"


def collect(args, env, api=None, fetcher=fetch):
    queries = ray.load_json(args.queries) if args.queries else {}
    if not isinstance(queries, dict) or len(queries) > 50 or any(
            not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", k)
            or not isinstance(v, str) or not v.strip() for k, v in queries.items()):
        raise ValueError("Queries must map safe IDs to expressions, at most 50")
    start = timestamp(args.start) if args.start is not None else None
    end = timestamp(args.end) if args.end is not None else None
    if (start is None) != (end is None) or (queries and start is None):
        raise ValueError("Range queries require both start and end")
    if not math.isfinite(args.step) or args.step <= 0 or (start is not None and (
            end <= start or (end - start) / args.step > 10000)):
        raise ValueError("Window and step must be bounded and positive")
    base = env.get("PROMETHEUS_URL", "")
    # Validate supplied endpoints before creating artifacts or making requests.
    urls = {key: query_url(base, expression, start, end, args.step) for key, expression in queries.items()}
    if api is None:
        api = ray.RayAPI(env.get("RAY_DASHBOARD_URL", ""), env.get("RAY_AUTH_TOKEN", ""))
    output = Path(args.output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    manifest = {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
                "window": {"start": start, "end": end, "step_seconds": args.step},
                "ray_snapshot": "UNAVAILABLE", "metrics": {},
                "logs": "NOT_COLLECTED", "grafana": "NOT_INSPECTED",
                "window_validity": "UNKNOWN"}
    try:
        ray.private_json(output / "ray-state.json", api.request())
        manifest["ray_snapshot"] = "AVAILABLE"
    except (ray.TuningError, ValueError, TypeError, OSError):
        manifest["ray_snapshot"] = "ERROR"
    for key, url in urls.items():
        try:
            response = fetcher(url, env.get("PROMETHEUS_AUTH_TOKEN", ""))
            ray.private_json(output / (key + ".json"), response)
            manifest["metrics"][key] = {"status": availability(response), "expression": queries[key],
                                        "artifact": key + ".json"}
        except (ValueError, TypeError, OSError, urllib.error.URLError, ray.TuningError):
            manifest["metrics"][key] = {"status": "ERROR", "expression": queries[key]}
    ray.private_json(output / "collection.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", help="Private JSON mapping IDs to verified PromQL")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--step", type=float, default=15)
    parser.add_argument("--output", required=True, help="New private artifact directory")
    args = parser.parse_args()
    try:
        manifest = collect(args, os.environ)
    except (ValueError, TypeError, OSError, ray.TuningError):
        print("Collection failed; check URLs, window, query IDs and fresh output directory.", file=sys.stderr)
        return 1
    failed = manifest["ray_snapshot"] == "ERROR" or any(m["status"] != "AVAILABLE" for m in manifest["metrics"].values())
    print("Evidence saved privately; window validity still requires log/telemetry review.")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
