"""Load a native GuideLLM JSON/YAML spec and bind runtime connections."""
import copy
import csv
import json
import math
from pathlib import Path

from runtime_config import inference_environment, connection_manifest, evaluation_settings


def read_spec(path):
    source = Path(path).resolve()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        raise ValueError("Cannot read --spec") from None
    try:
        if source.suffix.lower() == ".json":
            data = json.loads(text)
        elif source.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                raise RuntimeError("YAML specs need PyYAML; use the GuideLLM container or a JSON spec") from None
            data = yaml.safe_load(text)
        else:
            raise ValueError("--spec must be a JSON or YAML file")
    except RuntimeError:
        raise
    except (ValueError, TypeError):
        raise ValueError("Cannot parse --spec as JSON/YAML") from None
    except Exception:
        raise ValueError("Cannot parse --spec as JSON/YAML") from None
    if not isinstance(data, dict):
        raise ValueError("The spec must be an object")
    # Accept the flat BenchmarkArgs form shown in the integration example as well
    # as GuideLLM's native {metadata, spec, benchmarks} scenario form.
    if "spec" not in data:
        data = {"metadata": data.get("metadata", {}),
                "spec": {key: value for key, value in data.items() if key not in ("metadata", "benchmarks")},
                **({"benchmarks": data["benchmarks"]} if "benchmarks" in data else {})}
    return data, source


def _local_paths(value, directory):
    if isinstance(value, dict):
        if str(value.get("kind", "")).endswith("_file") and isinstance(value.get("path"), str):
            path = Path(value["path"]).expanduser()
            if not path.is_absolute():
                value["path"] = str((directory / path).resolve())
        if value.get("kind") == "huggingface_auto" and isinstance(value.get("model"), str):
            model = value["model"]
            if model.startswith(("./", "../", "/", "~")):
                value["model"] = str((directory / Path(model).expanduser()).resolve())
        for item in value.values():
            _local_paths(item, directory)
    elif isinstance(value, list):
        for item in value:
            _local_paths(item, directory)


def context_check(spec, env):
    """Check known synthetic/trace lengths; describe gaps for other datasets."""
    if not env.get("CONTEXT_TOKENS"):
        return {"status": "NOT_CONFIGURED", "note": "Confirm the model context limit before using long prompts"}
    try:
        limit = int(env["CONTEXT_TOKENS"])
        margin = int(env.get("CONTEXT_MARGIN", "256"))
    except ValueError:
        raise ValueError("CONTEXT_TOKENS and CONTEXT_MARGIN must be integers") from None
    if limit <= 0 or margin < 0:
        raise ValueError("Context limit must be positive; margin must be nonnegative")
    status = "PASS"
    for data in spec.get("data", []):
        if not isinstance(data, dict):
            raise ValueError("Each data entry must be an object")
        sizes = []
        if data.get("kind") == "synthetic_text":
            def specified(*names, default=None):
                return next((data[name] for name in names if data.get(name) is not None), default)
            prompt = specified("prompt_tokens_max", "prompt_tokens")
            output = specified("output_tokens_max", "output_tokens")
            first_prompt = specified("first_prompt_tokens_max", "first_prompt_tokens", default=prompt)
            first_output = specified("first_output_tokens_max", "first_output_tokens", default=output)
            turns, prefix = specified("turns", default=1), specified("prefix_tokens", default=0)
            values = (prompt, output, first_prompt, first_output, turns, prefix)
            if all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in values):
                sizes = [first_prompt + first_output + max(0, turns - 1) * (prompt + output) + prefix]
            else:
                status = "PARTIAL"
            if any(key in data for key in ("branches", "tool_call_turns")) or any(
                    key.endswith("_stdev") and value for key, value in data.items()):
                status = "PARTIAL"
        elif data.get("kind") == "trace_synthetic" and data.get("source", {}).get("kind") == "csv_file":
            try:
                with Path(data["source"]["path"]).open(newline="") as stream:
                    sizes = [int(row["input_length"]) + int(row["output_length"]) for row in csv.DictReader(stream)]
            except (OSError, ValueError, KeyError):
                raise ValueError("Cannot check input_length/output_length in the local trace CSV") from None
            if not sizes:
                status = "PARTIAL"
        else:
            status = "PARTIAL"
        if any(size + margin > limit for size in sizes):
            raise ValueError("The native workload exceeds CONTEXT_TOKENS including output caps and context margin")
    return {"status": status, "context_tokens": limit, "context_margin": margin,
            "note": "Checks known token budgets; chat templates, sampled lengths and complex graphs require review"}


def prepare_spec(path, env, output_dir):
    data, source = read_spec(path)
    scenario = copy.deepcopy(data)
    spec = scenario.get("spec")
    if not isinstance(spec, dict) or not isinstance(spec.get("backend"), dict):
        raise ValueError("The spec needs a backend object")
    backend = spec["backend"]
    if backend.get("kind", "openai_http") != "openai_http":
        raise ValueError("This runner supports the openai_http backend")
    if backend.get("api_key"):
        raise ValueError("Remove backend.api_key from the spec; supply the selected key through the environment")
    backend.pop("api_key", None)
    if backend.get("verify", True) is not True:
        raise ValueError("backend.verify must be true; supply CERT_FILE for a private CA")
    overrides = scenario.get("benchmarks", [])
    if not isinstance(overrides, list) or any(item is not None and not isinstance(item, dict) for item in overrides):
        raise ValueError("benchmarks must be a list of override objects or null")
    for override in overrides:
        if any(key.split(".")[0].split("[")[0] in ("backend", "outputs") for key in (override or {})):
            raise ValueError("Per-benchmark backend/outputs overrides are unsupported; use separate spec runs")
    resolved = inference_environment(env, backend)
    backend.update(kind="openai_http", target=resolved["AI_ENDPOINT"], model=resolved["AI_MODEL"], verify=True)
    request_format = backend.setdefault("request_format", "/v1/chat/completions")
    if request_format not in ("/v1/chat/completions", "/v1/completions", "/v1/responses"):
        raise ValueError("The probe supports chat completions, completions, and responses specs")
    resolved["PROBE_REQUEST_FORMAT"] = request_format
    route = backend.get("api_routes", {}).get(request_format, request_format)
    if not isinstance(route, str) or not route.startswith("/") or route.startswith("//") or "?" in route or "#" in route:
        raise ValueError("The probe route must be an absolute path on the selected endpoint")
    resolved["PROBE_ROUTE"] = route
    if backend.get("timeout") is not None:
        resolved["REQUEST_TIMEOUT_SECONDS"] = str(backend["timeout"])
    if not isinstance(spec.get("profile"), dict) or not isinstance(spec.get("data"), list) or not spec["data"]:
        raise ValueError("The spec needs a profile and a nonempty data list")
    constraints = spec.get("constraints", [])
    if not isinstance(constraints, list) or not any(
            isinstance(item, dict) and item.get("kind") in ("max_requests", "max_duration") for item in constraints):
        raise ValueError("The spec needs a max_requests or max_duration constraint")
    for item in constraints:
        if not isinstance(item, dict):
            raise ValueError("Each constraint must be an object")
        if item.get("kind") in ("max_requests", "max_duration"):
            limit = item.get("count" if item["kind"] == "max_requests" else "seconds")
            if not isinstance(limit, (int, float)) or isinstance(limit, bool) or not math.isfinite(limit) or limit <= 0:
                raise ValueError("Request and duration limits must be finite and positive")
    _local_paths(spec, source.parent)
    _local_paths(overrides, source.parent)
    context = context_check(spec, env)
    # Keep all workload fields unchanged; this wrapper owns the report destination.
    spec["outputs"] = [{"kind": kind, "path": str(Path(output_dir) / ("benchmarks." + kind))}
                       for kind in ("json", "csv", "html")]
    manifest = {"guidellm_version": "0.8.0", "workload_source": "native_spec",
                "spec_file": str(source), "connections": connection_manifest(resolved),
                "profile": copy.deepcopy(spec["profile"]), "constraints": copy.deepcopy(constraints),
                "tokenizer": copy.deepcopy(spec.get("tokenizer")),
                "context_check": context,
                "eval_settings": evaluation_settings(env)}
    return scenario, manifest, resolved
