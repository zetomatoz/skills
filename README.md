# Inference Engineering Skills

**Practical agent skills for benchmarking, operating, and improving LLM inference.**

A growing collection of runnable workflows for **Ray, GuideLLM, vLLM, and the
inference stack around them**. Give your coding agent a repeatable procedure,
run the supporting tools yourself, and keep the evidence needed to understand
what changed.

The goal: make inference engineering easier to reproduce, review, and share—from
a first load test to a carefully measured serving configuration change.

[Explore the first skill](inference-stress-testing/README.md) ·
[Request a skill](https://github.com/zetomatoz/skills/issues) ·
[Contribute](#contribute)

## Skill directory

| Skill | What you can do today | Tools |
|---|---|---|
| [Inference stress testing](inference-stress-testing/README.md) | Generate paired prompt/output workloads, benchmark a streaming endpoint at 12 and 24 concurrent requests, evaluate results, and optionally tune an existing Ray Serve deployment. | GuideLLM 0.8.0, Docker Compose, Ray Serve REST API |

**Current scope:** one runnable skill. It targets OpenAI-compatible inference
endpoints, including compatible vLLM deployments. Dedicated vLLM deployment and
optimization skills are planned; they are not included yet.

## Why use these skills?

- **Runnable procedures.** Each skill pairs agent instructions with scripts,
  configuration, and a guide you can use directly.
- **Reproducible experiments.** Preserve workloads, seeds, versions, and thresholds
  so configuration comparisons have a useful baseline.
- **Inspectable results.** The current benchmark saves workload manifests,
  JSON/CSV/HTML reports, and evaluation summaries.
- **Clear evidence.** Validation records distinguish local tests, mock integration
  checks, and measurements against real models. Unconfigured performance gates
  remain explicit.

## Quick start

You need Git and Docker with Compose. A live benchmark also needs a reachable
inference endpoint, its model name, and a matching tokenizer.

```bash
git clone https://github.com/zetomatoz/skills.git
cd skills/inference-stress-testing
cp .env.example .env
```

Edit `.env`: set `AI_ENDPOINT`, `AI_MODEL`, `TOKENIZER`, and the model's actual
`CONTEXT_TOKENS`. Add credentials if your endpoint or tokenizer requires them.

```bash
# Generate the workload and scenario without contacting the inference endpoint.
docker compose run --rm runner plan

# Probe, warm up, benchmark, and evaluate the configured endpoint.
docker compose run --rm runner run
```

Inspect the new directory under `artifacts/` for the manifest, reports, evaluation,
and summary. The load generator needs no GPU; the inference server supplies the
compute. The default workload includes long prompts, so check the
[test specification](inference-stress-testing/references/test-spec.md) before running.

For thresholds, networking, TLS, and Ray tuning, read the
[complete guide](inference-stress-testing/README.md).

## Use with your agent

Each skill has a `SKILL.md` entry point and its supporting files. For a Codex project,
copy the entire skill directory into your project's skill directory. Run this from
the repository root, replacing the destination with your project path:

```bash
mkdir -p /path/to/your-project/.agents/skills
cp -R inference-stress-testing /path/to/your-project/.agents/skills/
```

Example request:

> Use the inference-stress-testing skill to benchmark my endpoint at 12 and 24
> concurrent requests. Keep the same workload for both stages, report p95 time to
> first token and output throughput, and identify any unconfigured evaluation gates.

For other agents, use their skill-loading mechanism or point them to the
[skill instructions](inference-stress-testing/SKILL.md). The supporting tools can
also run standalone through Docker Compose.

## Validation you can inspect

The first skill has 23 standard-library tests and a recorded container integration
check using GuideLLM's mock server. That verifies the integration; it does not
establish real-model throughput, GPU capacity, or production readiness.

Read the [validation record](inference-stress-testing/references/validation.md),
[test specification](inference-stress-testing/references/test-spec.md), and
[upstream sources](inference-stress-testing/references/sources.md) for the evidence
and assumptions behind the workflow.

## Where this collection is heading

Contributions and requests are welcome in these areas. These are roadmap ideas,
not shipped features:

| Area | Useful skills to build |
|---|---|
| Ray Serve | Deployment diagnosis, replica sizing, autoscaling experiments, and configuration comparisons. |
| GuideLLM | Workload design, concurrency sweeps, latency/throughput analysis, and repeatable benchmark reports. |
| vLLM | Serving setup, memory and KV-cache diagnosis, batching, parallelism, and prefix-cache experiments. |
| Inference operations | Endpoint probes, capacity planning, observability, regression detection, and cost/performance comparisons. |

## Contribute

Help make this a useful public reference for inference engineers and the agents
they work with:

- **Request a workflow:** [open an issue](https://github.com/zetomatoz/skills/issues)
  with the task, stack and versions, desired outcome, and how you would verify it.
- **Share a fix or a skill:** [open a pull request](https://github.com/zetomatoz/skills/pulls).
  Include `SKILL.md`, a README with runnable examples, supporting tools, upstream
  references, and validation instructions. State required credentials and any
  deployment changes explicitly.
- **Bring evidence:** separate mock checks from real-model results. For performance
  claims, include hardware, model/tokenizer revisions, serving versions, workload,
  cache policy, and measurement limits. Remove credentials and private request data.

Keep each skill in its own directory so users can install it independently. Prefer
focused workflows with clear inputs and outputs. Small, well-verified contributions
are welcome.

If this collection helps your work, star it and share a workflow you want to see next.

## Repository checks

From the repository root:

```bash
python3 scripts/check_links.py
python3 scripts/check_links.py --external
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s inference-stress-testing/tests -v
```

GitHub Actions checks documentation links and static file references on pushes and
pull requests. The external check also verifies public HTTP links. Generated
artifacts and user-supplied configuration files are not expected to exist in the repo.
