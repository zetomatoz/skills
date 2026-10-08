#!/usr/bin/env python3
"""Evaluate GuideLLM 0.8 report schema v2 using only the Python standard library.

Latency gates use successful requests. Error rate includes incomplete requests.
Every benchmark must pass independently; aggregate averages cannot hide a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping


# GuideLLM uses seconds for request_latency, milliseconds for TTFT and ITL.
METRICS = {
    "p95_ttft_ms": ("time_to_first_token_ms", "percentiles.p95", 1, "EVAL_P95_TTFT_MS", "max"),
    "p95_itl_ms": ("inter_token_latency_ms", "percentiles.p95", 1, "EVAL_P95_ITL_MS", "max"),
    "p95_e2e_ms": ("request_latency", "percentiles.p95", 1000, "EVAL_P95_E2E_MS", "max"),
    "output_tps": ("output_tokens_per_second", "mean", 1, "EVAL_MIN_OUTPUT_TPS", "min"),
}


def _get(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict) or key not in data:
            raise ValueError(f"Missing metric: {path}")
        data = data[key]
    return data


def _number(value: Any, name: str, *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    if integer and int(value) != value:
        raise ValueError(f"{name} must be an integer")
    return int(value) if integer else value


def _threshold(env: Mapping[str, str], key: str, default: str | None = None) -> float | None:
    value = env.get(key, default)
    if value is None or str(value).strip() == "":
        value = default
    if value is None:
        return None
    try:
        return float(_number(float(value), key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {key}: expected a finite nonnegative number") from exc


def _gate(observed: float | None, threshold: float | None, direction: str) -> dict:
    if threshold is None:
        return {"status": "NOT_CONFIGURED", "observed": observed, "threshold": None}
    passed = observed is not None and (
        observed <= threshold if direction == "max" else observed >= threshold
    )
    return {"status": "PASS" if passed else "FAIL", "observed": observed,
            "threshold": threshold, "comparison": "<=" if direction == "max" else ">="}


def _length_audit(benchmark: dict) -> dict:
    """Inspect retained requests without treating max_tokens as actual output."""
    samples = benchmark.get("requests", {}).get("successful", [])
    if not isinstance(samples, list):
        samples = []
    groups: dict[int, dict] = {}
    reported, estimates, unknown = 0, 0, 0
    for request in samples:
        if not isinstance(request, dict):
            unknown += 1
            continue
        usage = request.get("output_metrics") or {}
        actual = usage.get("total_tokens") if isinstance(usage, dict) else None
        if actual is None:
            # output_tokens may be a one-token-per-stream-chunk approximation.
            if request.get("output_tokens") is not None:
                estimates += 1
            else:
                unknown += 1
            continue
        try:
            actual = _number(actual, "reported output tokens", integer=True)
            reported += 1
            args = request.get("request_args")
            args = json.loads(args) if isinstance(args, str) else args
            body = args.get("body", {}) if isinstance(args, dict) else {}
            cap = next((body[k] for k in ("max_completion_tokens", "max_tokens", "max_output_tokens")
                        if body.get(k) is not None), None)
            if cap is None:
                continue
            cap = _number(cap, "requested output cap", integer=True)
            if cap == 0:
                continue
        except (TypeError, ValueError, AttributeError):
            continue
        group = groups.setdefault(cap, {"requested_output_cap_tokens": cap, "samples": 0,
                                       "reported_output_tokens_sum": 0, "below_cap": 0,
                                       "at_cap_possible_truncation": 0, "above_cap": 0})
        group["samples"] += 1
        group["reported_output_tokens_sum"] += actual
        group["below_cap" if actual < cap else "at_cap_possible_truncation" if actual == cap else "above_cap"] += 1
    for group in groups.values():
        group["reported_output_tokens_mean"] = group["reported_output_tokens_sum"] / group["samples"]
    return {
        "status": "AVAILABLE" if groups else "UNAVAILABLE",
        "successful_request_samples": len(samples),
        "samples_with_reported_usage": reported,
        "samples_with_only_stream_iteration_estimates": estimates,
        "samples_with_unknown_usage": unknown,
        "by_requested_output_cap": [groups[key] for key in sorted(groups)],
        "notes": [
            "Requested output tokens are caps; actual generation may stop earlier.",
            "GuideLLM 0.8 does not preserve finish_reason: reaching the cap indicates possible truncation, not proof.",
            "Retained request samples may include warmup/cooldown and differ from the measured request totals.",
            "Missing server usage can make GuideLLM token metrics depend on stream-iteration estimates.",
        ],
    }


def evaluate_report(data: Any, env: Mapping[str, str] | None = None) -> dict:
    """Return a JSON-safe PASS/FAIL result; malformed reports fail closed.

    Optional unset SLOs are NOT_CONFIGURED. This is a performance evaluation,
    not a model quality evaluation. Each report benchmark is checked separately.
    """
    env = os.environ if env is None else env
    result: dict = {"status": "FAIL", "report_schema": "guidellm-0.8/schema-v2",
                   "errors": [], "benchmarks": [],
                   "semantics": {"error_rate": "(errored + incomplete) / measured total",
                                 "output_tps": "successful aggregate output tokens per second (GuideLLM rate mean)",
                                 "latencies": "successful requests; TTFT and ITL ms, E2E converted seconds to ms",
                                 "itl": "GuideLLM token-weighted per-request average inter-token latency distribution",
                                 "quality": "not evaluated by this script"}}
    try:
        thresholds = {name: _threshold(env, definition[3]) for name, definition in METRICS.items()}
        thresholds["error_rate"] = _threshold(env, "EVAL_MAX_ERROR_RATE", "0")
        thresholds["completed_requests"] = _threshold(env, "EVAL_MIN_COMPLETED_REQUESTS", "100")
        if thresholds["error_rate"] > 1:
            raise ValueError("EVAL_MAX_ERROR_RATE must be a fraction between 0 and 1")
        minimum = thresholds["completed_requests"]
        if minimum < 1 or minimum != int(minimum):
            raise ValueError("EVAL_MIN_COMPLETED_REQUESTS must be a positive integer")
        metadata = _get(data, "metadata")
        if not isinstance(metadata, dict) or metadata.get("version") != 2:
            raise ValueError("Expected GuideLLM report metadata.version=2")
        if not str(metadata.get("guidellm_version", "")).startswith("0.8."):
            raise ValueError("This evaluator supports GuideLLM 0.8.x; verify schema before changing versions")
        benchmarks = _get(data, "benchmarks")
        if not isinstance(benchmarks, list) or not benchmarks:
            raise ValueError("Report contains no benchmarks")
    except (TypeError, ValueError) as exc:
        result["errors"].append(str(exc))
        return result

    for index, benchmark in enumerate(benchmarks):
        entry: dict = {"index": index, "status": "FAIL", "errors": [], "metrics": {}, "gates": {}}
        result["benchmarks"].append(entry)
        if not isinstance(benchmark, dict):
            entry["errors"].append("Benchmark must be an object")
            continue
        for name in METRICS:
            entry["metrics"][name] = None
        try:
            totals = _get(benchmark, "metrics.request_totals")
            counts = {status: _number(_get(totals, status), f"request_totals.{status}", integer=True)
                      for status in ("successful", "errored", "incomplete", "total")}
            entry["request_totals"] = counts
            if counts["total"] != sum(counts[s] for s in ("successful", "errored", "incomplete")):
                raise ValueError("Request totals do not add up")
            if counts["total"] == 0 or counts["successful"] == 0:
                raise ValueError("No successfully completed measured requests")
            entry["metrics"]["error_rate"] = (counts["errored"] + counts["incomplete"]) / counts["total"]
            entry["metrics"]["completed_requests"] = counts["successful"]
        except (TypeError, ValueError) as exc:
            entry["errors"].append(str(exc))
        for name, (metric, statistic, multiplier, _, _) in METRICS.items():
            try:
                distribution = _get(benchmark, f"metrics.{metric}.successful")
                count = _number(_get(distribution, "count"), f"{metric}.count", integer=True)
                if count == 0:
                    raise ValueError(f"{metric} has no successful observations")
                value = _number(_get(distribution, statistic), metric) * multiplier
                value = _number(value, name)
                if name == "output_tps" and value <= 0:
                    raise ValueError("Successful output throughput must be positive")
                entry["metrics"][name] = value
            except (TypeError, ValueError) as exc:
                entry["errors"].append(str(exc))
            entry["gates"][name] = _gate(entry["metrics"][name], thresholds[name], METRICS[name][4])
        for name, direction in (("error_rate", "max"), ("completed_requests", "min")):
            entry["gates"][name] = _gate(entry["metrics"].get(name), thresholds[name], direction)
        entry["gates"]["metric_integrity"] = {"status": "FAIL" if entry["errors"] else "PASS"}
        entry["output_length_audit"] = _length_audit(benchmark)
        if not entry["errors"] and all(g["status"] != "FAIL" for g in entry["gates"].values()):
            entry["status"] = "PASS"
    if all(b["status"] == "PASS" for b in result["benchmarks"]):
        result["status"] = "PASS"
    return result


def markdown_summary(result: dict) -> str:
    lines = [f"# Performance evaluation: {result['status']}", "",
             "Unset optional thresholds are NOT_CONFIGURED. Model quality is evaluated separately.", ""]
    lines.extend(f"- {error}" for error in result["errors"])
    for benchmark in result["benchmarks"]:
        lines += [f"## Benchmark {benchmark['index']}: {benchmark['status']}", "",
                  "| Gate | Status | Observed | Threshold |", "|---|---|---:|---:|"]
        for name, gate in benchmark["gates"].items():
            lines.append(f"| {name} | {gate['status']} | {gate.get('observed', '')} | {gate.get('threshold', '')} |")
        lines += [""] + [f"- {error}" for error in benchmark["errors"]] + [""]
    lines += ["Output cap / reported usage comparisons are in evaluation.json. Cap hits indicate possible truncation only.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("evaluation.json"))
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    try:
        with args.report.open() as handle:
            data = json.load(handle)
        result = evaluate_report(data)
    except (OSError, ValueError) as exc:
        result = {"status": "FAIL", "errors": [f"Cannot read report: {exc}"], "benchmarks": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_summary(result))
    print(f"{result['status']}: {args.output}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
