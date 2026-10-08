#!/usr/bin/env python3
"""Offline, conservative throughput screen for matching profile suites."""
import argparse
import json
import math
import os
from pathlib import Path
import sys


def read(folder, name):
    with (Path(folder) / name).open() as stream:
        return json.load(stream)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid comparison number")
    return value


def inspect_run(folder):
    manifest = read(folder, "manifest.json")
    context = read(folder, "experiment-context.json")
    fields = {"profile_id", "model_revision", "tokenizer_revision", "serving_image", "ray_version",
              "engine_version", "hardware", "cache_policy", "generation_settings", "measurement_policy",
              "required_gates", "quality_kind"}
    if not isinstance(context, dict) or set(context) != fields:
        raise ValueError("Incomplete invariant context")
    if any(not isinstance(context[k], str) or not context[k].strip() for k in fields - {
            "generation_settings", "measurement_policy", "required_gates"}):
        raise ValueError("Missing system identity")
    if not isinstance(context["generation_settings"], dict) or not isinstance(context["measurement_policy"], dict):
        raise ValueError("Invalid invariant settings")
    required = context["required_gates"]
    if not isinstance(required, list) or any(k not in {"p95_ttft_ms", "p95_itl_ms", "p95_e2e_ms", "output_tps"} for k in required):
        raise ValueError("Unknown required gate")
    status, quality = read(folder, "status.json"), read(folder, "quality.json")
    observation = read(folder, "observation.json")
    evaluation = read(folder, "evaluation.json")
    if status.get("live_benchmark_run") is not True or status.get("status") != "PASS":
        raise ValueError("No passing live benchmark")
    if quality.get("status") != "PASS" or quality.get("kind") != context["quality_kind"]:
        raise ValueError("Quality policy did not pass")
    if observation.get("window_validity") != "VALID":
        raise ValueError("Window not verified valid")
    stages = evaluation.get("benchmarks")
    if evaluation.get("status") != "PASS" or not isinstance(stages, list) or not stages:
        raise ValueError("Performance evaluation did not pass")
    if not isinstance(manifest, dict) or len(manifest.get("streams", [])) != len(stages):
        raise ValueError("Stage and stream counts differ")
    for index, stage in enumerate(stages):
        if stage.get("index") != index or stage.get("status") != "PASS" or stage.get("errors"):
            raise ValueError("Malformed stage")
        gates = stage.get("gates", {})
        if any(g.get("status") == "FAIL" for g in gates.values()) or any(
                gates.get(k, {}).get("status") != "PASS" for k in [*required, "metric_integrity", "error_rate", "completed_requests"]):
            raise ValueError("Required gate missing or not passing")
        metrics = stage["metrics"]
        for key in ("p95_ttft_ms", "p95_itl_ms", "p95_e2e_ms", "error_rate", "completed_requests"):
            number(metrics[key])
        if number(metrics["output_tps"]) <= 0:
            raise ValueError("No throughput")
    return manifest, context, stages


def compare(baselines, candidates, minimum=0.03, regression=0):
    if len(baselines) != len(candidates) or not baselines:
        raise ValueError("Supply matching nonempty profile suites")
    if number(minimum) <= 0 or number(regression) >= 1:
        raise ValueError("Improvement must be positive; regression must be below 1")
    result = {"schema_version": 1, "decision": "INCONCLUSIVE", "profiles": [],
              "errors": [], "minimum_improvement": minimum, "maximum_throughput_regression": regression,
              "note": "Screen only: repeats, drift, full quality and causal review remain required."}
    improved, rejected, seen = False, False, set()
    for baseline, candidate in zip(baselines, candidates):
        try:
            bm, bc, bs = inspect_run(baseline)
            cm, cc, cs = inspect_run(candidate)
            if bm != cm or bc != cc or len(bs) != len(cs):
                raise ValueError("Profiles or invariant settings differ")
            if bc["profile_id"] in seen:
                raise ValueError("Duplicate profile ID")
            seen.add(bc["profile_id"])
            profile = {"profile_id": bc["profile_id"], "stages": [],
                       "unconfigured_gates": sorted(k for k, v in bs[0]["gates"].items()
                                                    if v.get("status") == "NOT_CONFIGURED")}
            for index, (before, after) in enumerate(zip(bs, cs)):
                # Same gates, thresholds and direction; observations may differ.
                bg = {k: {x: v.get(x) for x in ("threshold", "comparison")} for k, v in before["gates"].items()}
                cg = {k: {x: v.get(x) for x in ("threshold", "comparison")} for k, v in after["gates"].items()}
                if bg != cg:
                    raise ValueError("Evaluation policy differs")
                change = after["metrics"]["output_tps"] / before["metrics"]["output_tps"] - 1
                improved |= change >= minimum
                rejected |= change < -regression
                profile["stages"].append({"streams": bm["streams"][index], "throughput_change_fraction": change,
                                           "baseline_metrics": before["metrics"], "candidate_metrics": after["metrics"]})
            result["profiles"].append(profile)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            result["errors"].append("A run is incomplete, invalid, or incomparable; inspect its private evidence.")
    if not result["errors"]:
        result["decision"] = "REJECT" if rejected or not improved else "ACCEPTABLE_FOR_CONFIRMATION"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="append", required=True)
    parser.add_argument("--candidate", action="append", required=True)
    parser.add_argument("--min-improvement", type=float, default=0.03)
    parser.add_argument("--max-throughput-regression", type=float, default=0)
    parser.add_argument("--output", required=True, help="New private decision file")
    args = parser.parse_args()
    try:
        result = compare(args.baseline, args.candidate, args.min_improvement, args.max_throughput_regression)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (ValueError, TypeError, OSError):
        print("Comparison failed; supply matched profiles and a new output file.", file=sys.stderr)
        return 1
    print(result["decision"])
    return 0 if result["decision"] == "ACCEPTABLE_FOR_CONFIRMATION" else 2


if __name__ == "__main__":
    sys.exit(main())
