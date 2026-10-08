"""Runtime connections and dotenv loading; never serialize credentials."""
import os
from pathlib import Path
import re
import shlex
import ssl
from urllib.parse import urlsplit


def load_environment(path=None, environ=None):
    """Load .env without expansion, then let the process environment win."""
    source = Path(path) if path is not None else Path(".env")
    result = {}
    if source.is_file():
        for number, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            name, separator, value = line.partition("=")
            name, value = name.strip(), value.strip()
            if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
                raise ValueError(f"Invalid dotenv assignment on line {number}")
            if value.startswith(("'", '"')):
                try:
                    parts = shlex.split(value, comments=True, posix=True)
                except ValueError:
                    raise ValueError(f"Invalid dotenv quoting on line {number}") from None
                if len(parts) != 1:
                    raise ValueError(f"Invalid dotenv value on line {number}")
                value = parts[0]
            else:
                value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
            result[name] = value
    elif path is not None:
        raise ValueError("Cannot read --env-file")
    result.update(os.environ if environ is None else environ)
    return result


def base_url(value, name):
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError(f"{name} must be an HTTP(S) base URL without credentials, query, or fragment")
    return value.rstrip("/")


def inference_environment(env, backend=None):
    """Resolve only the selected target's credential, keeping legacy inputs usable."""
    result = dict(env)
    backend = backend or {}
    target = env.get("BENCH_TARGET", "").strip()
    if not target:
        if env.get("AI_ENDPOINT"):
            target = "legacy"
        elif env.get("ENDPOINT_PROXY"):
            target = "proxy"
        elif env.get("ENDPOINT_INFERENCE_BACKEND"):
            target = "inference_backend"
        else:
            target = "spec"
    choices = {
        "proxy": ("ENDPOINT_PROXY", "PROXY_API_KEY"),
        "inference_backend": ("ENDPOINT_INFERENCE_BACKEND", "INFERENCE_BACKEND_API_KEY"),
        "openai": ("ENDPOINT_OPENAI", "OPENAI_API_KEY"),
        "legacy": ("AI_ENDPOINT", "AI_API_KEY"),
        "spec": (None, "AI_API_KEY"),
    }
    if target not in choices or (env.get("BENCH_TARGET") and target in ("legacy", "spec")):
        raise ValueError("BENCH_TARGET must be proxy, inference_backend, or openai")
    endpoint_name, key_name = choices[target]
    endpoint = env.get(endpoint_name, "") if endpoint_name else backend.get("target", "")
    if target == "openai" and not endpoint:
        endpoint = env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    result["AI_ENDPOINT"] = base_url(endpoint, endpoint_name or "backend.target").removesuffix("/v1")
    result["AI_API_KEY"] = env.get(key_name, "")
    result["AI_MODEL"] = backend.get("model") or env.get("AI_MODEL", "")
    if not isinstance(result["AI_MODEL"], str) or not result["AI_MODEL"].strip():
        raise ValueError("Set backend.model in the spec, or AI_MODEL for a generated workload")
    result["RESOLVED_BENCH_TARGET"] = target
    if env.get("ENDPOINT_CONTROL_PLANE"):
        base_url(env["ENDPOINT_CONTROL_PLANE"], "ENDPOINT_CONTROL_PLANE")
    return result


def trusted_environment(env):
    result = dict(env)
    if env.get("CERT_FILE"):
        certificate = Path(env["CERT_FILE"]).expanduser().resolve()
        if not certificate.is_file():
            raise ValueError("CERT_FILE must point to a readable CA bundle; use its container path in Docker")
        result.update(CERT_FILE=str(certificate), SSL_CERT_FILE=str(certificate),
                      REQUESTS_CA_BUNDLE=str(certificate))
    return result


def tls_context(env):
    try:
        return ssl.create_default_context(cafile=env.get("CERT_FILE") or env.get("SSL_CERT_FILE") or None)
    except (OSError, ssl.SSLError):
        raise ValueError("Cannot load the configured CA bundle") from None


def connection_manifest(env):
    """A deliberate allowlist: neither keys nor the full environment are saved."""
    return {"target": env["RESOLVED_BENCH_TARGET"], "endpoint": env["AI_ENDPOINT"],
            "model": env["AI_MODEL"], "certificate_configured": bool(env.get("CERT_FILE") or env.get("SSL_CERT_FILE")),
            "control_plane_endpoint": env.get("ENDPOINT_CONTROL_PLANE") or None,
            "control_plane_used_by_benchmark": False}


def evaluation_settings(env):
    names = ("EVAL_MAX_ERROR_RATE", "EVAL_MIN_COMPLETED_REQUESTS", "EVAL_P95_TTFT_MS",
             "EVAL_P95_ITL_MS", "EVAL_P95_E2E_MS", "EVAL_MIN_OUTPUT_TPS")
    return {key: env[key] for key in names if key in env}
