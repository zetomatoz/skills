# Select knobs from evidence

Match the installed engine and Ray versions; defaults and supported settings change.
Use the [Ray deployment configuration](https://docs.ray.io/en/latest/serve/configure-serve-deployment.html)
and [vLLM engine arguments](https://docs.vllm.ai/en/latest/configuration/engine_args/)
for their schemas. Values below are experiment dimensions, not recommended defaults.

| Layer | Controls | Question to test |
|---|---|---|
| Ray capacity | `num_replicas`, autoscaling bounds/targets | Does more capacity improve the target load within hardware and cost limits? |
| Ray admission | `max_ongoing_requests`, queue limits | Does admission reduce latency or merely move waiting upstream? |
| Ray placement | Actor resources, placement groups | Can each engine worker actually obtain the required GPUs on suitable nodes? |
| Engine topology | Tensor/pipeline/data parallelism | Does a different sharding/replication layout fit weights and cache while improving the workload? |
| Engine batching | `max_num_seqs`, `max_num_batched_tokens` | Does more batching improve useful throughput without hurting TTFT or memory? |
| Engine memory | `max_model_len`, `gpu_memory_utilization`, KV dtype | Is capacity limited by memory, and does the change preserve context and quality? |
| Engine decode | Model-supported speculative decoding | Does acceptance outweigh draft work on this model and hardware? |
| Routing/cache | Prefix caching and supported affinity policy | Does reuse outweigh per-replica imbalance at the intended load? |

For a simple homogeneous TP-only layout, replicas × TP is a first GPU budget check.
Include PP, DP, auxiliary workers, placement constraints, and existing allocations
for the real layout. A reservation alone does not change engine worker topology.
Model fit and per-node memory must also pass; do not treat all cluster GPUs as one
shared memory pool. Keep required context length fixed, including output headroom.
Do not lower it merely to obtain an easier benchmark.

## Lessons adapted from the visually inspected original

The source was a particular four-GPU deployment. Its settings and historical
results are hypotheses to retest, not portable baselines or locally verified claims.

- Prefix affinity helped growing conversations at modest concurrency, yet an
  earlier high-concurrency run stalled with idle GPUs and queued requests. Compare
  reuse, replica imbalance, and queueing under the real workload before weakening
  or removing affinity. Synthetic independent requests cannot settle that tradeoff.
- Raising ongoing-request limits, sequence limits, or batch tokens reduced useful
  throughput in some long-context trials. Bigger limits are not automatically
  better; measure prefill pressure, decode latency, KV occupancy, and queue time.
- More replicas with lower TP improved some short/high-concurrency workloads;
  fewer replicas with more sharding served other context/capacity needs. Recheck
  model fit, cache capacity, placement, and actual demand for each topology.
- KV offload exhausted shared memory when each replica allocated a large buffer.
  Verify the backend's allocation semantics and aggregate node RAM/shared-memory
  budget across replicas before enabling it. Validate KV dtype and speculative
  decoding support and quality on the installed model/version.
- Preserve reasoning settings, sampling, parsers, and token caps while tuning
  capacity. Changing them can change both work performed and output correctness.

## Diagnosis

| Observed evidence | Next check |
|---|---|
| High TTFT, idle GPUs, skewed replica queues | Routing affinity, admission, upstream waiting, replica availability |
| High TTFT, busy GPUs, growing queues | Prefill/decode saturation, batch limits, capacity, topology |
| STARTING replicas without active actors | Placement/resource feasibility, node health, GPU allocation and worker logs |
| OOM, crash loops, restarts | Weights/cache/batch memory, hardware/driver health; invalidate interrupted runs |
| Simultaneous stream resets or gateway errors with healthy Ray | Proxy/network/node events; correlate timestamps before assigning cause |
| Malformed tool JSON after an output cap | Confirm truncation and subsequent client handling with a reproduction |

HTTP status alone does not establish a root cause. Keep infrastructure failures
in endpoint reliability totals even when excluded from a clean configuration
comparison. Do not rank a candidate using successful-request latency alone.
Count unknown errors against acceptance; exclude a benchmark artifact only with
reproducible evidence, preserving both raw and classified counts. Never dismiss
every 400 as truncation or every 502 as a proxy issue.
