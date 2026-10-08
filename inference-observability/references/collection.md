# Collect and interpret evidence

Run from this skill's directory. The collector uses only Python's standard library
and the sibling benchmark skill's REST transport. Export `RAY_DASHBOARD_URL` and
optional `RAY_AUTH_TOKEN` without printing them. `.env` is not loaded automatically.

```bash
python3 scripts/collect_metrics.py --output artifacts/before-01
# After measurement, collect a Ray snapshot and optional historical metrics.
python3 scripts/collect_metrics.py --start 1791482400 --end 1791482700 \
  --queries /private/path/queries.json --output artifacts/after-01
```

For range queries, also export `PROMETHEUS_URL` and optionally
`PROMETHEUS_AUTH_TOKEN`. `queries.json` is an object mapping descriptive IDs to
PromQL expressions verified on your backend. It has no built-in engine metric names.
Choose `--step` in seconds (default 15) appropriate to scrape resolution and the
test duration. Use Unix seconds or timezone-aware ISO timestamps for start/end.
The collector saves mode-0600 raw artifacts and an availability manifest. An empty
result, nonfinite sample, partial response or failed query is not a zero metric.
It preserves backend warnings and series labels, and never averages percentiles.
It takes a snapshot now; it cannot recover Ray state from a historical time window.

Separate start/end snapshots from periodic samples. Use new output directories.
When running in parallel with load, the observer polls only reads; do not run
another load generator or configuration writer. Keep credentials and query labels
out of public reports, and use trusted CA configuration rather than bypassing TLS.

## Logs and panels

[Ray get_log](https://docs.ray.io/en/latest/ray-observability/reference/doc/ray.util.state.get_log.html)
supports bounded log retrieval through the installed Ray client. Match the cluster
version if using it; the dependency-free collector intentionally does not guess
version-specific log routes. Discover node/actor IDs and log files first, then use
the dashboard or an installed compatible client with `follow=False` and finite
`tail`/timeout. Gateway authentication may require the dashboard route instead.
The collector does not automate logs or Grafana navigation.

For each relevant Grafana panel record datasource, filters, timezone, time range,
metric definition, units and aggregation. Compare warmup and measured intervals
separately. Inspect controller/replica events, queues, GPU utilization/memory,
prefill/decode latency, KV occupancy and prefix-cache reuse when available.

## Metric semantics

Cache occupancy and prefix-cache hit rate answer different questions. Hit ratio
needs a hits/eligible-lookups denominator over the same interval, not arbitrary
counter division. Use rates for counters and handle resets. Histograms need an
appropriate quantile query; averaging replica p95s does not produce cluster p95.
Correlate useful output tokens/s with errors and actual output lengths. Backend
latency may exclude proxy time; client and server percentiles are not interchangeable.

Sources: [Prometheus range API](https://prometheus.io/docs/prometheus/latest/querying/api/),
[Ray Serve API](https://docs.ray.io/en/latest/serve/api/index.html), and the installed
engine's own metric documentation. Backend adapters must supply metric mappings,
labels, units and availability; NVIDIA Dynamo is a future adapter, not implemented.
