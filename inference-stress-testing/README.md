# Inference Engineering - Agent skills

Docker runner and reusable agent skills for the supplied sketch, pinned to GuideLLM
0.8.0. Synthetic paired workloads: **15/15/30/35/5%**, tested at **12 and 24 streams**.
See [the complete test spec](references/test-spec.md) for assumptions and limits.

## Run

Requires Docker with Compose. No GPU is needed by the load generator; the target
inference server supplies compute. Copy this entire folder into your agent's skills
directory (for Codex, `.agents/skills/inference-stress-testing/`) to install it as a skill.
It also runs standalone:

```bash
cp .env.example .env
# Edit AI_ENDPOINT, AI_MODEL, TOKENIZER and the actual CONTEXT_TOKENS in .env.
# On Linux, also set LOCAL_UID / LOCAL_GID to id -u / id -g if not 1000.
docker compose run --rm runner plan
docker compose run --rm runner run
```

`plan` creates a seeded CSV of token lengths, a GuideLLM scenario and a manifest;
it does not contact an endpoint. GuideLLM's `trace_synthetic` loader generates text
from these lengths using the configured tokenizer. Every complete 200-row trace
contains exactly 30/30/60/70/10 paired requests, shuffled with SEED. Both measured
profiles use that workload. A time-limited prefix or failed requests can differ.
Use a request count divisible by 20 for the default weights.

`run` checks the pinned runtime version, probes the endpoint, checks optional simple
correctness, warms up separately, executes the mixed workload, and writes evaluation
results. Exit 0 means all configured checks passed; 2 means a check or execution
failed. Unset latency/throughput gates are explicitly NOT_CONFIGURED. The default
minimum is 100 successful measured requests per stage; increase duration if long
requests hit the time bound first. QUALITY_EVAL=0 skips exact-answer checks but keeps
an API probe. The main benchmark always streams, even though the tiny probe does not.

Each run has a fresh `artifacts/<timestamp>/` directory containing the scenario,
manifest, workload CSV, raw JSON/CSV/HTML reports, quality results, performance
evaluation, and Markdown summary. Inspect `status.json` after failures. Request
samples may contain generated text; artifact directories are private by default.
The runtime API key is stored only in a temporary mode-0600 scenario and removed.

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
For a corporate CA, add a read-only bundle mount to Compose and set SSL_CERT_FILE
and REQUESTS_CA_BUNDLE to the mounted bundle path; do not disable verification.
Use HF_TOKEN for gated tokenizer downloads or mount the tokenizer under this folder.
Adjust RUNNER_CPUS/RUNNER_MEMORY if local generation competes with the load client.

For production benchmarking, check that the generator is not CPU-bound, preserve
cache policy across comparisons, and record hardware, server versions, model and
tokenizer revisions. Synthetic text controls size; it does not represent task quality.

## Local verification

```bash
python -m unittest discover -s tests -v
```

See [verification evidence](references/validation.md) and [sources](references/sources.md).

Publication drafts for review: [tweet thread](editorial/tweet-thread.md) and
[Substack article](editorial/substack-draft.md). Nothing has been published.
