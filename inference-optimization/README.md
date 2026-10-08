# Inference optimization

One bounded workflow composing [stress tests](../inference-stress-testing/README.md),
[observation](../inference-observability/README.md), and
[Ray tuning](../ray-autotune-inference/README.md). Each skill remains directly callable.
Start with [SKILL.md](SKILL.md) and the [experiment contract](references/experiment.md).

The workflow is agent-guided: Python tools collect metrics, edit config, call Ray
and screen comparisons; the agent supplies bottleneck hypotheses, manages the
ledger, coordinates tests and reviews telemetry. It is not an unattended optimizer.
Ray is the first backend; NVIDIA Dynamo is an extension contract only.

Example: “Use inference-optimization on my Ray deployment for these fixed profile
env files. Optimize output throughput subject to my p95 latency and quality gates.
You may tune and restore this test environment. Stop after five candidates or
two hours and repeat the finalist three times.”

No live optimization has been validated. Offline tests cover collector responses,
comparison gates and plugin packaging in addition to the existing Ray/helper tests.
