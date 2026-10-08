---
name: inference-observability
description: Observe a Ray-managed inference system during a bounded test window, correlate replica health and logs with Prometheus or Grafana latency, queue, GPU and cache metrics, and report evidence and gaps without changing deployments.
---

# Observe inference

Use independently for diagnosis or alongside inference-stress-testing. This skill
is read-only. Ray is the implemented control-plane adapter; Prometheus-compatible
metrics and Grafana panels are optional. Do not restart replicas or tune knobs.

1. Identify the authorized Ray app/deployment, dashboard, engine/version, endpoint,
   test run ID and UTC measurement window. Discover which metrics, labels and logs
   are actually exposed. Read [collection guidance](references/collection.md).
2. Capture Ray state before and after each workload stage, and periodically during
   it when useful. Use the Python collector or dashboard. Capture actor/replica IDs,
   restarts, unhealthy/starting states, placement constraints and queue imbalance.
   Two snapshots alone cannot prove nothing restarted between them.
3. Query the available metrics backend for the same window. Supply explicit PromQL
   mapped to the deployment and version; do not assume universal metric names.
   Review TTFT, TPOT/ITL, end-to-end latency, request/error/output rates, per-replica
   queue/load, GPU utilization/memory, KV occupancy and prefix-cache hit rate.
   Keep units, aggregation and source labels. Missing telemetry is UNAVAILABLE,
   never zero. TPOT (time per output token) and ITL can have different semantics;
   confirm a dashboard's “TOPT” label before equating it with either.
4. Inspect worker, replica, controller and proxy logs for the test window. Prefer
   the Ray dashboard log links or the installed version's supported State API.
   Use bounded tails, record node/actor/file and timezone, and protect logs containing
   request data or credentials. Do not guess file paths or delete diagnostic data.
5. When Grafana is supplied, navigate the relevant panels with browser/computer
   tools, set absolute test times and correct app/model/instance filters, and retain
   panel names, visible units/queries, screenshot locations and capture time. Do
   not claim a panel was inspected when only its URL was supplied. API metrics can
   substitute for visual panels with that distinction stated.
6. Correlate errors, latency/queue changes and restarts by timestamp. Distinguish
   measured facts, probable explanations and unresolved causes. Report window
   validity as VALID, INVALID or UNKNOWN. State which metrics/logs/panels are absent
   and what that prevents concluding. A health snapshot is not a performance test.

Deliver private raw artifacts plus an observation report: window, system/version,
sources, metric availability/units, replica/log events, invalidation evidence,
likely bottleneck, and a narrowly framed next tuning hypothesis. Never change
deployment settings as part of observation.
