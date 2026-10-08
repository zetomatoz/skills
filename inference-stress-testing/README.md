# Inference Engineering - Agent skills

Docker runner and reusable agent skill for inference endpoint benchmarks, pinned to
GuideLLM 0.8.0. Synthetic paired workloads: **15/15/30/35/5%**, tested at **12 and 24 streams**.
See [the complete test spec](references/test-spec.md) for assumptions and limits.

## Start with GitHub Copilot

Copy this entire folder into your project's `.github/skills/inference-stress-testing/`
for Copilot, or `.agents/skills/inference-stress-testing/` for Codex. Open the project
in VS Code and use Copilot Chat in Agent mode. Docker with Compose must be running
on the machine where the agent executes terminal commands. No load-generator GPU
or separate GuideLLM installation is needed.

Work from the installed skill directory:

```bash
cp .env.example .env
```

In `.env`, set `BENCH_TARGET`, its endpoint and key, and the actual `CONTEXT_TOKENS`.
In [smoke.json](assets/specs/smoke.json), set `backend.model` to the served model name
and `tokenizer.model` to its matching tokenizer. The smoke is deliberately small:
one stream, 20 requests, 128 prompt tokens, and a 32-token output cap.

```bash
docker compose run --rm runner plan --spec assets/specs/smoke.json --run-name first-test
docker compose run --rm -e EVAL_MIN_COMPLETED_REQUESTS=20 runner run --spec assets/specs/smoke.json --run-name first-test
```

The YAML equivalent is [smoke.yaml](assets/specs/smoke.yaml); change `--spec` to that
path. A Copilot prompt for the same workflow:

> Use inference-stress-testing. Read my existing .env without displaying secrets.
> Use assets/specs/smoke.json, check the endpoint/model/tokenizer and Docker, then
> generate an offline plan. When I ask you to run it, use a minimum-completed gate
> of 20 for this smoke and summarize the new artifacts.

`plan` is offline: it does not send inference requests or contact a control plane.
`run` checks the pinned GuideLLM version and native schema, probes the endpoint,
runs a separate warmup, executes the spec and evaluates each measured benchmark.
Warmup stops at its time limit or the retained request bound, whichever comes first.
Exit 0 means all configured checks passed; 2 means a check or execution failed.
Unset latency/throughput gates are explicitly NOT_CONFIGURED. `QUALITY_EVAL=0`
retains an API probe while skipping the three tiny exact-answer checks.

## Runtime connections and credentials

| Variable | Purpose |
|---|---|
| `BENCH_TARGET` | `proxy`, `inference_backend`, or `openai` |
| `ENDPOINT_PROXY` / `PROXY_API_KEY` | Proxy inference base URL and bearer credential |
| `ENDPOINT_INFERENCE_BACKEND` / `INFERENCE_BACKEND_API_KEY` | Direct inference base URL and bearer credential |
| `ENDPOINT_OPENAI` / `OPENAI_API_KEY` | OpenAI target; a blank endpoint uses `https://api.openai.com/v1` |
| `ENDPOINT_CONTROL_PLANE` / `CONTROL_PLANE_API_KEY` | Optional connection inputs for a deployment adapter; benchmark plan/run never calls this API |
| `CERT_FILE` | Optional trusted CA bundle; TLS verification remains enabled |
| `HF_TOKEN` | Optional credential for gated tokenizer downloads |

The generic control-plane URL is independent of `RAY_DASHBOARD_URL` and
`RAY_AUTH_TOKEN`. The bundled deployment adapter uses Ray's Serve REST API;
a custom control plane needs its own documented routes/client. Credentials for
one target are never substituted for another target's missing key.

Compose loads `.env` and explicitly forwards the connection variables from your
shell with shell values taking precedence. For example, a `PROXY_API_KEY` already
in the shell need not be copied into `.env`. A one-off override is also supported:

```bash
docker compose run --rm -e BENCH_TARGET=inference_backend runner run --spec assets/specs/smoke.json
```

The Python entrypoint also loads an optional `.env` itself. Use `--env-file` for a
specific file; process variables win, including explicitly empty values. It accepts
single/double quotes, `export`, and comments, and treats values literally without
shell execution or variable expansion. JSON plans can be generated without Docker:

```bash
python scripts/run.py plan --env-file .env --spec assets/specs/smoke.json --run-name first-test
```

In an environment with GuideLLM 0.8.0 installed and `guidellm` on `PATH`, the same
Python entrypoint also supports `run` directly. Use an endpoint reachable from that
machine and set the smoke's minimum-completed gate to 20 in `.env`:

```bash
python scripts/run.py run --env-file .env --spec assets/specs/smoke.json --run-name first-test
```

YAML parsing needs PyYAML, which the GuideLLM image supplies. Local file references
in the spec resolve relative to the spec file, while `CERT_FILE` resolves relative
to the working directory. Files passed to Compose must be inside its mounted skill
folder or explicitly mounted into the container.

## Native GuideLLM specs and mixed calls

`--spec` accepts a native `{metadata, spec, benchmarks}` scenario or a flat spec
with `backend`, `tokenizer`, `profile`, `data`, `data_loader`, and `constraints`.
The spec owns model/tokenizer selection, multi-turn settings, distributions, seed,
concurrency and limits. The runner binds the selected endpoint, enables certificate
verification and redirects JSON/CSV/HTML reports into the fresh artifact directory.
Environment workload settings such as `STREAMS` and `PROMPT_TOKENS` do not override
an explicit spec. Keep credentials out of specs. Per-benchmark backend/output
overrides are rejected; use a separate spec run for each endpoint/model.

The included [mixed.json](assets/specs/mixed.json) references a seeded
[paired trace](assets/workloads/mixed.csv) with 200 rows, exactly 30/30/60/70/10
requests across the five prompt/output buckets. GuideLLM's `trace_synthetic` loader
generates text using the configured tokenizer. The same trace runs at 12 and then
24 streams, interleaving all buckets. Set its model/tokenizer and confirm the long
requests fit the model before running. Use a minimum-completed gate of 100 for this
profile rather than the small smoke's 20.

`CONTEXT_TOKENS` and `CONTEXT_MARGIN` check local trace lengths and simple synthetic
budgets, including ordinary accumulated multi-turn history. Other data sources,
sampled lengths, tool calls and complex conversation graphs require manual review;
the manifest records partial or missing checks. Output caps do not guarantee output
length. A duration-limited or failed measured subset can differ from the full mix.

The existing generated-mix workflow remains available without `--spec`:

```bash
# Uses AI_MODEL, TOKENIZER, STREAMS, PROMPT_TOKENS, OUTPUT_TOKENS, and other workload vars.
docker compose run --rm runner plan
docker compose run --rm runner run
```

Legacy `.env` files with `AI_ENDPOINT`, `AI_MODEL`, `AI_API_KEY`, and `TOKENIZER`
still work when `BENCH_TARGET` is unset. The generator writes a seeded CSV, scenario
and manifest. Use a request count divisible by 20 for the default weights.

Each invocation creates a new `artifacts/<timestamp>-<run-name>/` directory (the
label is optional). `--output` accepts an explicit fresh directory. Inspect
`status.json`, `scenario.json`, `manifest.json`, raw reports, `quality.json`,
`evaluation.json`, and `summary.md`. Saved plans omit credentials; the selected API
key is injected into a mode-0600 temporary runtime scenario that is removed afterward.
Unrelated endpoint/admin credentials are not forwarded to the GuideLLM subprocess.
Reports and request samples remain private and may contain generated text.

To rerun evaluation after changing thresholds:

```bash
docker compose run --rm evaluate artifacts/RUN/benchmarks.json --output artifacts/RUN/reevaluation.json --markdown artifacts/RUN/reevaluation.md
```

## Tune an existing Ray deployment

Set RAY_DASHBOARD_URL, RAY_AUTH_TOKEN if needed, RAY_APP_NAME and
RAY_DEPLOYMENT_NAME. Save the complete current Serve JSON configuration as
`serve.json`, including all applications and global options. Blank resource
overrides preserve existing values. Set any of RAY_NUM_REPLICAS,
RAY_MAX_ONGOING_REQUESTS, RAY_NUM_CPUS, RAY_NUM_GPUS, then:

```bash
docker compose run --rm ray plan --output artifacts/ray-plan-01
# Inspect original.json and proposed.json in the private output directory.
docker compose run --rm ray apply --output artifacts/ray-apply-01
docker compose run --rm runner run
```

The helper uses GET/PUT `/api/serve/applications/`, preserves other apps, rejects
stale source configs, merges effective actor options, and checks readiness after
applying. Setting static replicas explicitly disables built-in autoscaling for that
deployment. Ray's API has no atomic compare-and-swap; use a single configuration
writer. It does not automatically restore the previous deployment after a benchmark.
Private original/proposed snapshots support deliberate recovery.

Direct REST tuning is for operator-managed Serve configurations. If KubeRay
RayService or another controller owns the configuration, update that source of
truth instead. Ray actor CPU/GPU values are reservations; they do not configure
vLLM tensor parallelism, placement groups, or GPU memory utilization.

GUIDELLM_IMAGE controls the load-generator image; EVAL_IMAGE controls the stdlib
evaluation/Ray helper image. Changing a **serving image** belongs to your existing
Docker/KubeRay deployment workflow. A generic Serve REST request cannot replace
the Ray cluster's container image. Record the serving image digest with each result.

## Network, TLS and resources

Container localhost is the container itself. Use host.docker.internal for a host
server or a resolvable remote/service URL. Keep the endpoint and tokenizer reachable
through your configured proxy. The backend has TLS verification explicitly enabled.
For a corporate CA, set `CERT_FILE` to the host bundle path and use the supplied
Compose override, which mounts it read-only and sets `CERT_FILE`, `SSL_CERT_FILE`
and `REQUESTS_CA_BUNDLE` to `/certificates/ca.pem` inside the container:

```bash
docker compose -f compose.yaml -f compose.cert.yaml run --rm runner plan --spec assets/specs/smoke.json
docker compose -f compose.yaml -f compose.cert.yaml run --rm -e EVAL_MIN_COMPLETED_REQUESTS=20 runner run --spec assets/specs/smoke.json
```

The override also supplies the CA to the Ray and evaluation services. Native Python
API probes, Ray calls and metrics collection use a verifying SSL context. A bundle
already inside the mounted skill folder can use a container-readable `CERT_FILE`
without the extra mount. Never disable verification. Use `HF_TOKEN` for gated
tokenizer downloads or mount the tokenizer under this folder.
Adjust RUNNER_CPUS/RUNNER_MEMORY if local generation competes with the load client.

For production benchmarking, check that the generator is not CPU-bound, preserve
cache policy across comparisons, and record hardware, server versions, model and
tokenizer revisions. Synthetic text controls size; it does not represent task quality.

## Local verification

```bash
python -m unittest discover -s tests -v
```

See [verification evidence](references/validation.md) and [sources](references/sources.md).
