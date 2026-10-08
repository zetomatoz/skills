# Inference Engineering Skills

Runnable agent skills for benchmarking inference endpoints, collecting serving
metrics, tuning existing Ray Serve deployments, and comparing bounded experiments.
Each skill includes instructions, supporting tools, and validation records.

## Skill directory

| Skill | What you can do today | Tools |
|---|---|---|
| [Inference stress testing](inference-stress-testing/README.md) | Generate paired prompt/output workloads, benchmark a streaming endpoint at 12 and 24 concurrent requests, evaluate results, and optionally tune an existing Ray Serve deployment. | GuideLLM 0.8.0, Docker Compose, Ray Serve REST API |
| [Ray autotune inference](ray-autotune-inference/README.md) | Inspect an existing deployment, run bounded knob experiments, verify health and rollback, and delegate endpoint measurements to inference-stress-testing. | Ray Serve, deployed inference engine, inference-stress-testing |
| [Inference observability](inference-observability/README.md) | Collect Ray state and windowed metrics, review logs and Grafana panels, and report bottlenecks and evidence gaps. | Python, Ray REST API, optional Prometheus/Grafana |
| [Inference optimization](inference-optimization/README.md) | Coordinate the stress-observe-tune-evaluate loop across fixed profiles with rollback, trial budgets and stopping rules. | All three skills, Python comparison tool |

**Current scope:** four independently callable skills and a buildable plugin that
bundles all dependencies, command aliases and focused agent specs. Ray is the first
control-plane backend. Observation and optimization are agent-guided workflows
supported by Python tools; logs/panels and live optimization are not yet validated.
Dedicated NVIDIA Dynamo and vLLM deployment adapters are not included.

## One plugin, individual skills or the full workflow

Build a self-contained [Inference Engineering plugin](plugins/inference-engineering/README.md):

```bash
python3 scripts/build_plugin.py --output dist/copilot/inference-engineering --zip
```

Choose stress-test, observe or tune independently, or invoke inference-optimization
to run a bounded experiment. GitHub Copilot CLI is the first supported harness, with native commands and
`.agent.md` definitions. The same procedures remain available as skills for Codex. No deployment or
load test starts on installation. See the plugin guide for host-specific loading,
private runtime workspaces, evidence limits and the backend extension contract.

## Quick start

You need Git and Docker with Compose. A live benchmark also needs a reachable
inference endpoint, its model name, and a matching tokenizer.

```bash
git clone https://github.com/zetomatoz/skills.git
cd skills/inference-stress-testing
cp .env.example .env
```

Edit `.env`: select `BENCH_TARGET=proxy` or `inference_backend`, set its
`ENDPOINT_PROXY` / `PROXY_API_KEY` or `ENDPOINT_INFERENCE_BACKEND` /
`INFERENCE_BACKEND_API_KEY`, and declare the model's actual `CONTEXT_TOKENS`.
Edit `assets/specs/smoke.json` with the served model name and matching tokenizer.
Set `CERT_FILE` when a private CA is needed; the skill guide includes the mount.

```bash
# Generate the workload and scenario without contacting the inference endpoint.
docker compose run --rm runner plan --spec assets/specs/smoke.json --run-name first-test

# Probe, warm up, benchmark, and evaluate the configured endpoint.
docker compose run --rm -e EVAL_MIN_COMPLETED_REQUESTS=20 runner run --spec assets/specs/smoke.json --run-name first-test
```

Inspect the new directory under `artifacts/` for the manifest, reports, evaluation,
and summary. The load generator needs no GPU; the inference server supplies the
compute. The small smoke starts at one stream and 20 requests. For the full mixed
workload, use `assets/specs/mixed.json` with a minimum-completed gate of 100. It
includes long prompts, so check the
[test specification](inference-stress-testing/references/test-spec.md) before running.

For thresholds, networking, TLS, and Ray tuning, read the
[complete guide](inference-stress-testing/README.md).

## Use with your agent

Each skill has a `SKILL.md` entry point and its supporting files. For Copilot in
VS Code, copy the entire folder into `.github/skills/inference-stress-testing/`
and use Copilot Chat in Agent mode. See [GitHub's skill instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills).
For a Codex project,
copy the entire skill directory into your project's skill directory. Run this from
the repository root, replacing the destination with your project path:

```bash
mkdir -p /path/to/your-project/.agents/skills
cp -R inference-stress-testing /path/to/your-project/.agents/skills/
```

Example request:

> Use inference-stress-testing with my native GuideLLM spec and existing .env.
> Generate an offline plan first. Use my selected endpoint and certificate settings
> without displaying credentials, and report any missing inputs or evaluation gates.

For other agents, use their skill-loading mechanism or point them to the
[skill instructions](inference-stress-testing/SKILL.md). The supporting tools can
also run standalone through Docker Compose.

## Validation you can inspect

The first skill has 34 unit checks and recorded mock integration checks, including
native JSON/YAML specs, runtime credentials and certificates. That verifies the integration; it does not
establish real-model throughput, GPU capacity, or production readiness.

Read the [validation record](inference-stress-testing/references/validation.md),
[test specification](inference-stress-testing/references/test-spec.md), and
[upstream sources](inference-stress-testing/references/sources.md) for the evidence
and assumptions behind the workflow.

## Contribute

Contributions should include runnable workflows and evidence of their behavior:

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
focused workflows with clear inputs and outputs.

## Repository checks

From the repository root:

```bash
python3 scripts/check_links.py
python3 scripts/check_links.py --external
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s inference-stress-testing/tests -v
python3 -m unittest discover -s ray-autotune-inference/tests -v
python3 -m unittest discover -s inference-observability/tests -v
python3 -m unittest discover -s inference-optimization/tests -v
```

GitHub Actions checks documentation links and static file references on pushes and
pull requests. The external check also verifies public HTTP links. Generated
artifacts and user-supplied configuration files are not expected to exist in the repo.
