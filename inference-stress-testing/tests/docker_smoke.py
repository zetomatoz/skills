"""Offline integration check inside the pinned image; no real model or GPU."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

from tokenizers import Tokenizer, models, pre_tokenizers
from transformers import PreTrainedTokenizerFast
from faker.providers.lorem.en_US import Provider

root = Path(__file__).resolve().parents[1]
temp = Path(tempfile.mkdtemp(prefix="guidellm-smoke-"))
vocab = {"[UNK]": 0}
for word in Provider.word_list:
    if word not in vocab:
        vocab[word] = len(vocab)
tokenizer = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
fast = PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]")
fast.save_pretrained(temp / "tokenizer")
env = dict(os.environ, AI_ENDPOINT="http://127.0.0.1:8000", AI_MODEL="test",
           TOKENIZER=str(temp / "tokenizer"), AI_API_KEY="", QUALITY_EVAL="0",
           STREAMS="12,24", PROMPT_TOKENS="16,24,32,48,64", OUTPUT_TOKENS="8,12,16,24,32",
           REQUESTS_PER_STAGE="20", DURATION_SECONDS="30", WARMUP_SECONDS="0",
           EVAL_MIN_COMPLETED_REQUESTS="20", CONTEXT_TOKENS="4096",
           HF_HOME=str(temp / "hf-cache"),
           TOKENIZERS_PARALLELISM="false", NO_PROXY="localhost,127.0.0.1",
           GUIDELLM__MAX_WORKER_PROCESSES="1", GUIDELLM__LOGGING__LOG_FILE=str(temp / "mock.log"))
with (temp / "server.log").open("w") as log:
    server = subprocess.Popen(["guidellm", "mock-server", "--host", "127.0.0.1",
        "--port", "8000", "--model", "test",
        "--ttft-ms", "1", "--itl-ms", "1", "--request-latency", "0.01"],
        stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("Mock server exited: " + (temp / "server.log").read_text()[-3000:])
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1):
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        if not ready:
            raise RuntimeError("Mock startup timed out")
        result = subprocess.run([sys.executable, str(root / "scripts/run.py"), "run",
                                "--output", str(root / ("artifacts/docker-smoke-" + str(int(time.time()))))], env=env, timeout=180)
        raise SystemExit(result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
