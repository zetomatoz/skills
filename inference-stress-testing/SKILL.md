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
   Use `.env.example` for generic runtime settings: `BENCH_TARGET`,
   `ENDPOINT_PROXY` / `PROXY_API_KEY`, `ENDPOINT_INFERENCE_BACKEND` /
   `INFERENCE_BACKEND_API_KEY`, and optionally `ENDPOINT_OPENAI` / `OPENAI_API_KEY`.
   Load the selected target only. Process variables take precedence over `.env`.
   The endpoint must be reachable from Docker.
   Do not invent a live endpoint or claim a mock result measures model performance.
2. Prefer the user's native GuideLLM JSON/YAML file via `--spec`. Keep its model,
   tokenizer, profile, data, multi-turn parameters, seed and limits unchanged.
   Bind only runtime connection/trust settings and fresh report paths. Both flat
   specs and `{metadata, spec, benchmarks}` scenarios are supported. Use
   `assets/specs/smoke.json` (or `.yaml`) for a small first trial; edit its model and
   matching tokenizer. Use `assets/specs/mixed.json` for the default paired mix.
   Without `--spec`, preserve the generated five paired buckets and weights;
   `AI_MODEL`, `TOKENIZER`, and environment workload controls still apply.
   Validate the model context window before sending long requests; review partial
   or missing context checks for complex/native workloads.
3. Run `docker compose run --rm runner plan --spec PATH --run-name NAME` when a
   spec is supplied (omit those optional arguments for the generated workflow).
   Inspect the manifest and scenario.
   This is offline: no inference requests and no Ray changes.
4. If tuning Ray is requested, use `docker compose run --rm ray plan --output
   artifacts/ray-plan-01`. Inspect its private proposed/original JSON files.
   Apply only within the user's authorized deployment scope with `ray apply`.
   Require the complete current Serve configuration; never drop unrelated apps.
   Resource reservations do not automatically change model parallelism or images.
5. Run `docker compose run --rm runner run --spec PATH --run-name NAME`, using the
   same input spec and connection settings as the plan. For the included 20-request
   smoke, add `-e EVAL_MIN_COMPLETED_REQUESTS=20` before `runner`; keep the default
   100-request minimum for the full mixed workload. It probes the endpoint, performs
   an optional tiny correctness smoke test, warms up separately, runs the supplied
   profiles (default mix: 12/24 streams in sequence), and evaluates each measured
   benchmark independently. Benchmark execution never contacts
   `ENDPOINT_CONTROL_PLANE`; Ray administration uses its own dashboard settings.
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

Do not bypass TLS verification. For corporate proxies, set `CERT_FILE` and use
`-f compose.yaml -f compose.cert.yaml` to mount the CA bundle read-only and forward
the container trust paths; see the README. Keep secrets out of native specs.
Legacy `AI_ENDPOINT` / `AI_API_KEY` are supported when `BENCH_TARGET` is unset.
Never commit `.env`,
private Serve configurations, or result directories containing request data.
