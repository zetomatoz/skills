---
name: inference-stress-testing
description: Build and run reproducible Docker-based GuideLLM mixed prompt/output load tests against OpenAI-compatible endpoints, evaluate performance and simple correctness, and optionally tune existing Ray Serve deployments through their REST API.
---

# GuideLLM mixed-load benchmark

Use this skill when asked to reproduce this mixed-load test, benchmark an inference
endpoint at 12/24 streams, compare serving configurations, or tune Ray Serve and
measure the result. Work from this skill's directory. Read `references/test-spec.md`
and `README.md` before running. The tested release is **GuideLLM 0.8.0**; its new
`guidellm run` interface replaces older `guidellm benchmark` examples.

## Workflow

1. Inspect supplied environment variables or `.env`. Never print credentials.
   Use `.env.example` for defaults. Required live inputs are `AI_ENDPOINT`,
   `AI_MODEL`, and a matching `TOKENIZER`. The endpoint must be reachable from Docker.
   Do not invent a live endpoint or claim a mock result measures model performance.
2. Preserve the five paired prompt/output buckets and weights from the spec.
   Exact token counts are explicit assumptions, configurable by environment.
   Validate the model context window before sending long requests.
3. Run `docker compose run --rm runner plan`. Inspect the manifest and scenario.
   This is offline: no inference requests and no Ray changes.
4. If tuning Ray is requested, use `docker compose run --rm ray plan --output
   artifacts/ray-plan-01`. Inspect its private proposed/original JSON files.
   Apply only within the user's authorized deployment scope with `ray apply`.
   Require the complete current Serve configuration; never drop unrelated apps.
   Resource reservations do not automatically change model parallelism or images.
5. Run `docker compose run --rm runner run`. It probes the endpoint, performs an
   optional tiny correctness smoke test, warms up separately, runs the 12/24 stream
   profiles in sequence, and evaluates each measured benchmark independently.
6. Inspect `status.json`, `quality.json`, `evaluation.json`, `summary.md`, and raw
   `benchmarks.json`. Report actual requests, latency, throughput, errors, configured
   gates, and missing gates. A workload output cap is not a guaranteed output length.
7. For comparisons, keep the tokenizer, workload, seed, limits, endpoint/model,
   cache policy, and evaluations fixed. Use fresh artifact directories; capture
   the serving image, model revision, GPU type/count, Ray/vLLM versions, and tuning
   proposal alongside each run. Do not automatically select or deploy a winner.

## Missing inputs and verification

When credentials or a live endpoint are absent, finish the plan and artifacts,
run available local checks, and state that a live benchmark has not run. Do not
block creation of this skill on optional preferences. Defaults are documented.
Run `python -m unittest discover -s tests -v` for the standard-library checks.

No runtime package installation is necessary: the Docker image supplies GuideLLM.
`GUIDELLM_IMAGE`, `EVAL_IMAGE`, runner resources, workload sizes, Ray overrides,
and evaluation gates are user-injected. Keep the pinned version until a newer
stable release has been checked against the scenario and report schemas.

Do not bypass TLS verification. For corporate proxies, mount the CA bundle and
set the appropriate Python trust variables; see the README. Never commit `.env`,
private Serve configurations, or result directories containing request data.
