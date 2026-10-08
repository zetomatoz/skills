"""Generate a tiny seeded trace; GuideLLM synthesizes its text with the tokenizer."""
import csv
import json
from pathlib import Path
import random
from probe import endpoint


def integers(env, name, default, length=None):
    values = [int(item.strip()) for item in env.get(name, default).split(",")]
    if (length and len(values) != length) or any(item <= 0 for item in values):
        raise ValueError(f"{name} needs {length or 'one or more'} positive integers")
    return values


def describe(env):
    prompts = integers(env, "PROMPT_TOKENS", "5000,20000,50000,50000,100000", 5)
    outputs = integers(env, "OUTPUT_TOKENS", "256,2048,512,2048,2048", 5)
    weights = integers(env, "MIX_WEIGHTS", "15,15,30,35,5", 5)
    if sum(weights) != 100:
        raise ValueError("MIX_WEIGHTS must sum to 100")
    count = int(env.get("REQUESTS_PER_STAGE", "200"))
    duration = int(env.get("DURATION_SECONDS", "300"))
    context = int(env.get("CONTEXT_TOKENS", "131072"))
    margin = int(env.get("CONTEXT_MARGIN", "256"))
    if count <= 0 or duration <= 0 or margin < 0:
        raise ValueError("Request/duration limits must be positive; margin nonnegative")
    if any(count * weight % 100 for weight in weights):
        raise ValueError("REQUESTS_PER_STAGE must represent every weight exactly (default mix: multiple of 20)")
    if any(p + o + margin > context for p, o in zip(prompts, outputs)):
        raise ValueError("A prompt + output + context margin exceeds CONTEXT_TOKENS")
    if not env.get("AI_MODEL") or not env.get("TOKENIZER"):
        raise ValueError("AI_MODEL and matching TOKENIZER are required")
    return {"guidellm_version": "0.8.0", "endpoint": endpoint(env),
            "model": env["AI_MODEL"], "tokenizer": env["TOKENIZER"],
            "streams": integers(env, "STREAMS", "12,24"),
            "seed": int(env.get("SEED", "42")), "requests_per_stage": count,
            "duration_seconds": duration, "context_tokens": context, "context_margin": margin,
            "bins": [{"bucket": i + 1, "prompt_tokens": p, "output_tokens": o,
                      "weight_percent": w, "trace_rows": count * w // 100}
                     for i, (p, o, w) in enumerate(zip(prompts, outputs, weights))],
            "mix_semantics": "Exact finite trace proportions; time limits, failures and scheduling can change the measured subset.",
            "eval_settings": {k: v for k, v in env.items() if k.startswith("EVAL_") and k != "EVAL_IMAGE"}}


def build_scenario(env, output_dir):
    info = describe(env)
    folder = Path(output_dir)
    rows = []
    for bucket in info["bins"]:
        rows.extend([{"timestamp": 0, "input_length": bucket["prompt_tokens"],
                      "output_length": bucket["output_tokens"], "bucket": bucket["bucket"]}]
                    * bucket["trace_rows"])
    random.Random(info["seed"]).shuffle(rows)
    trace = folder / "workload.csv"
    with trace.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp", "input_length", "output_length", "bucket"])
        writer.writeheader()
        writer.writerows(rows)
    return {"metadata": {"name": "mixed-prompt-output-12-24"}, "spec": {
        "backend": {"kind": "openai_http", "target": info["endpoint"], "model": info["model"],
                    "request_format": "/v1/chat/completions", "stream": True, "verify": True,
                    "validate_backend": False, "timeout": float(env.get("REQUEST_TIMEOUT_SECONDS", "120"))},
        "profile": {"kind": "concurrent", "streams": info["streams"]},
        "tokenizer": {"kind": "huggingface_auto", "model": info["tokenizer"]},
        "data": [{"kind": "trace_synthetic", "source": {"kind": "csv_file", "path": str(trace)}}],
        "data_loader": {"kind": "pytorch", "samples": info["requests_per_stage"], "shuffle": False, "prefetch_factor": 32},
        "constraints": [{"kind": "max_requests", "count": info["requests_per_stage"]},
                        {"kind": "max_duration", "seconds": info["duration_seconds"]}],
        "seed": {"kind": "static", "value": info["seed"]},
        "metrics": {"kind": "generative", "sample_size": 20},
        "outputs": [{"kind": kind, "path": str(folder / ("benchmarks." + kind))}
                    for kind in ("json", "csv", "html")]}}
