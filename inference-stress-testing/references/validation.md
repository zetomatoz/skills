# Verification evidence

Validated on 2026-10-07, America/Los_Angeles.

- 23 standard-library tests passed: workload correlation/proportions/reproducibility,
  context-limit rejection, report metrics/units/gates/schema failures, Ray app and
  resource preservation, stale configuration rejection, readiness, and private snapshots.
- Python compilation passed for all scripts.
- Docker Compose configuration validated using the example environment values.
- The official image reports GuideLLM 0.8.0. Its native `BenchmarkScenario` model
  accepted the generated default scenario.
- Full container smoke run passed using GuideLLM's own mock OpenAI-compatible
  server, a locally generated test tokenizer, and no external model/download.
  Both requested profiles (12 and 24 streams) completed 20 requests each, with
  zero errors and zero incomplete requests. All configured evaluation gates passed.
- The retained mock requests preserve the 3/3/6/7/1 distribution across output caps
  8/12/16/24/32 for each 20-request stage. JSON, CSV, HTML, and evaluation reports
  were generated. Optional latency thresholds were not configured for this smoke.

This validates the integration, not production capacity. The smoke uses short
prompts (16–64 tokens), a mock server, no GPU, and only 20 requests per stage, so it
does not establish sustained concurrency of 24 or test the 100k-token bucket.
The smoke's exact-answer quality checks are disabled because the server is a mock;
the API probe still runs. No live Ray cluster was mutated and no real-model
performance or semantic-quality benchmark was run.

Repeat the unit checks from the skill directory:

```bash
python -m unittest discover -s tests -v
```

Repeat the Docker integration check (creates a fresh timestamped artifact directory):

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work --entrypoint python \
  ghcr.io/vllm-project/guidellm:v0.8.0 tests/docker_smoke.py
```

The full-size scenario needs a supplied endpoint, API credentials when applicable,
matching tokenizer, and correctly declared context limit. Real Ray tuning needs
the operator's complete current Serve configuration and deployment identifiers.
