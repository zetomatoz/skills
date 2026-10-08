#!/usr/bin/env python3
"""Portable Docker entrypoint: plan, probe, warm up, benchmark, evaluate."""
import argparse
import copy
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from workload import build_scenario, describe
from probe import probe
from evaluate import evaluate_report, markdown_summary


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def execute(scenario, folder, env):
    runtime = copy.deepcopy(scenario)
    if env.get("AI_API_KEY"):
        runtime["spec"]["backend"]["api_key"] = env["AI_API_KEY"]
    # Secrets appear only in a private temporary file, never in argv or plan.json.
    fd, name = tempfile.mkstemp(prefix="guidellm-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(runtime, stream)
        child_env = dict(env)
        child_env["GUIDELLM__LOGGING__LOG_FILE"] = str(folder / "guidellm.log")
        result = subprocess.run(["guidellm", "run", "--config", name,
                                 "--disable-console-interactive"], env=child_env)
        if result.returncode:
            raise RuntimeError(f"GuideLLM failed with exit code {result.returncode}")
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "run"], nargs="?", default="plan")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    env = dict(os.environ)
    folder = (args.output or Path("artifacts") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    os.chmod(folder, 0o700)
    status = {"status": "PLANNED", "live_benchmark_run": False}
    try:
        scenario = build_scenario(env, folder)
        save(folder / "scenario.json", scenario)
        save(folder / "manifest.json", describe(env))
        print(f"Plan saved: {folder}", flush=True)
        if args.action == "plan":
            return 0
        version = importlib.metadata.version("guidellm")
        if version != "0.8.0":
            raise RuntimeError(f"Expected tested GuideLLM 0.8.0; found {version}")
        save(folder / "versions.json", {"guidellm": version, "python": sys.version,
                                       "image": env.get("GUIDELLM_IMAGE", "ghcr.io/vllm-project/guidellm:v0.8.0")})
        checks = probe(env)
        save(folder / "quality.json", checks)
        if checks["status"] != "PASS":
            raise RuntimeError("Endpoint/correctness smoke failed; see quality.json")
        seconds = int(env.get("WARMUP_SECONDS", "15"))
        if seconds < 0:
            raise ValueError("WARMUP_SECONDS must be nonnegative")
        if seconds:
            warm_dir = folder / "warmup"
            warm_dir.mkdir()
            warmup = copy.deepcopy(scenario)
            warmup.pop("benchmarks", None)
            warmup["spec"]["profile"] = {"kind": "concurrent", "streams": [1]}
            warmup["spec"]["constraints"] = [{"kind": "max_duration", "seconds": seconds}]
            warmup["spec"]["outputs"] = [{"kind": "json", "path": str(warm_dir / "benchmarks.json")}]
            print("Running separate warmup…", flush=True)
            execute(warmup, warm_dir, env)
        print("Running measured workload…", flush=True)
        status["live_benchmark_run"] = True
        execute(scenario, folder, env)
        report = json.loads((folder / "benchmarks.json").read_text())
        evaluation = evaluate_report(report, env)
        save(folder / "evaluation.json", evaluation)
        (folder / "summary.md").write_text(markdown_summary(evaluation))
        status["status"] = evaluation["status"]
        print(f"{status['status']}: {folder / 'summary.md'}", flush=True)
        return 0 if status["status"] == "PASS" else 2
    except Exception as exc:
        status.update(status="FAIL", error_type=type(exc).__name__)
        if isinstance(exc, (ValueError, RuntimeError)):
            status["error"] = str(exc)
        # All raised local validation messages are safe; never print API bodies.
        print(f"Run failed ({type(exc).__name__}): {status.get('error', 'see artifacts')} [{folder}]", file=sys.stderr)
        return 2
    finally:
        save(folder / "status.json", status)


if __name__ == "__main__":
    raise SystemExit(main())
