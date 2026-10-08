"""Local mock integration inside GuideLLM 0.8.0; no real model or GPU."""
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import time
import urllib.request
import yaml

from tokenizers import Tokenizer, models, pre_tokenizers
from transformers import PreTrainedTokenizerFast
from faker.providers.lorem.en_US import Provider

root = Path(__file__).resolve().parents[1]
temp = Path(tempfile.mkdtemp(prefix="guidellm-smoke-"))
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
base = f"http://127.0.0.1:{port}"
vocab = {"[UNK]": 0}
for word in Provider.word_list:
    if word not in vocab:
        vocab[word] = len(vocab)
tokenizer = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
fast = PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]")
fast.save_pretrained(temp / "tokenizer")
env = dict(os.environ, AI_ENDPOINT=base, AI_MODEL="test", BENCH_TARGET="",
           ENDPOINT_PROXY="", ENDPOINT_INFERENCE_BACKEND="", CERT_FILE="",
           TOKENIZER=str(temp / "tokenizer"), AI_API_KEY="", QUALITY_EVAL="0",
           STREAMS="12,24", PROMPT_TOKENS="16,24,32,48,64", OUTPUT_TOKENS="8,12,16,24,32",
           REQUESTS_PER_STAGE="20", DURATION_SECONDS="30", WARMUP_SECONDS="0",
           EVAL_MIN_COMPLETED_REQUESTS="20", CONTEXT_TOKENS="4096",
           HF_HOME=str(temp / "hf-cache"),
           TOKENIZERS_PARALLELISM="false", NO_PROXY="localhost,127.0.0.1",
           GUIDELLM__MAX_WORKER_PROCESSES="1", GUIDELLM__LOGGING__LOG_FILE=str(temp / "mock.log"))
with (temp / "server.log").open("w") as log:
    server = subprocess.Popen(["guidellm", "mock-server", "--host", "127.0.0.1",
        "--port", str(port), "--model", "test",
        "--ttft-ms", "1", "--itl-ms", "1", "--request-latency", "0.01"],
        stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("Mock server exited: " + (temp / "server.log").read_text()[-3000:])
            try:
                with urllib.request.urlopen(base + "/health", timeout=1):
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        if not ready:
            raise RuntimeError("Mock startup timed out")
        output = root / ("artifacts/runtime-smoke-" + str(time.time_ns()))
        output.mkdir(parents=True, mode=0o700)
        generated = output / "generated"
        command = [sys.executable, str(root / "scripts/run.py"), "run"]
        result = subprocess.run(command + ["--output", str(generated)], env=env, timeout=180)
        if result.returncode:
            raise SystemExit(result.returncode)
        native = json.loads((generated / "scenario.json").read_text())
        for suffix in ("json", "yaml"):
            spec_file = temp / ("native." + suffix)
            spec_file.write_text(json.dumps(native) if suffix == "json" else yaml.safe_dump(native))
            target = "proxy" if suffix == "json" else "inference_backend"
            runtime_env = dict(env, BENCH_TARGET=target, ENDPOINT_PROXY=base,
                               PROXY_API_KEY="mock-proxy-key", ENDPOINT_INFERENCE_BACKEND=base,
                               INFERENCE_BACKEND_API_KEY="mock-backend-key",
                               ENDPOINT_CONTROL_PLANE="https://control.example.invalid",
                               CONTROL_PLANE_API_KEY="mock-admin-key", WARMUP_SECONDS="15")
            folder = output / ("native-" + suffix)
            result = subprocess.run(command + ["--spec", str(spec_file), "--run-name", target,
                                               "--output", str(folder)], env=runtime_env, timeout=180)
            if result.returncode:
                raise SystemExit(result.returncode)
            for artifact in folder.rglob("*.json"):
                content = artifact.read_text()
                assert all(key not in content for key in ("mock-proxy-key", "mock-backend-key", "mock-admin-key")), artifact.name
            report = json.loads((folder / "benchmarks.json").read_text())
            assert [benchmark["metrics"]["request_totals"]["successful"] for benchmark in report["benchmarks"]] == [20, 20]
        print(f"Generated, native JSON/proxy, native YAML/backend and separate warmups passed: {output}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
