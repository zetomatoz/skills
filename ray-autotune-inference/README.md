# Ray autotune inference

A bounded agent workflow for tuning an existing Ray Serve inference deployment:
inspect → baseline → change one knob → verify → stress test → compare → restore
or retain a verified configuration within the user's authorized scope.

Read [SKILL.md](SKILL.md) as the entry point. It delegates OpenAI-compatible endpoint
load generation and evaluation to [inference-stress-testing](../inference-stress-testing/README.md).
This skill has no separate workload specs or benchmark runner, and does not use
the Ray Tune optimizer library.

Install both folders together in your agent's skills directory. The companion
skill supplies Docker Compose, GuideLLM, and shared Ray REST transport.
This skill adds native Python tools for offline config editing and Ray status,
live planning, applying the saved candidate, and explicit rollback.

Example request:

> Use ray-autotune-inference to tune my existing Ray Serve deployment. Optimize
> output throughput while preserving p95 TTFT and correctness. Plan at most five
> candidates, change one knob per trial, and use inference-stress-testing to load
> test the same OpenAI-compatible endpoint and workload after each change.

Provide the complete current deployment configuration, its owning control plane,
known-good rollback configuration, target app/deployment, GPU topology, endpoint,
model/tokenizer, versions, and performance constraints. Credentials stay in local
environment configuration. Plan-only work is possible without live access.

The [deployment guide](references/deployment.md) covers supported helper commands
and rollback limitations. The [knob guide](references/knobs.md) covers topology,
batching, memory, routing, and evidence-based diagnosis.

This is a focused adaptation of the user's original skill, read visually through
Citrix. Historical tuning lessons were retained without private endpoints,
credentials, certificates, workload assets, or platform-specific recovery APIs.
Local validation checks structure, links, nine new state-transition tests, and
the existing helper tests; no live
Ray deployment or real-model performance has been validated for this adaptation.

Run the offline tests from the repository root:

```bash
python3 -m unittest discover -s ray-autotune-inference/tests -v
```
