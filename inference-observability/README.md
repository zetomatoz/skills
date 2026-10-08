# Inference observability

Read-only observation of Ray-managed inference: state snapshots, windowed metrics,
log review and optional Grafana panel inspection. Use [SKILL.md](SKILL.md) alone or
as the observation step of [inference optimization](../inference-optimization/SKILL.md).
The [collection guide](references/collection.md) documents the Python collector
and the separate dashboard/log workflow. Install sibling inference-stress-testing
for shared REST transport. No metrics backend or dashboard is assumed to exist.

Ray and Prometheus collection are automated; log and Grafana review remain
agent-guided using available dashboard/State API tools. Missing sources are explicit.
Local tests use fixtures/mocked transport; no live cluster or Grafana has been tested.
