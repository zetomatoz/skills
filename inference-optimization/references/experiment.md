# Experiment contract

Create a private session directory containing a session JSON and append-only
`trials.jsonl`. Keep it outside the installed plugin tree, which may be read-only.
Record: session/backend/target identity; authorized operations; stable config path
and SHA-256; fixed profile IDs and environment/manifest hashes; objective; required
latency/error/quality gates; trial, load and wall-time limits; minimum improvement;
plateau patience; repeat count; incumbent; stopping/final-state policy.

Each profile is an explicit set of the companion runner's environment values:
model/tokenizer/context, five paired prompt/output buckets and weights, stream
levels, seed, duration/request caps, timeout, warmup, quality and evaluation gates.
The existing mixed runner still requires five buckets; other workload types need
their own validated runner adapter. Supply different profile env files for long
context, decode-heavy, short-request or other mixes. Run every required profile on
every candidate. Do not change profile thresholds after seeing candidate results.

Capture an `experiment-context.json` beside every run with exactly:

```json
{
  "profile_id": "short-mixed",
  "model_revision": "operator-supplied-revision",
  "tokenizer_revision": "operator-supplied-revision",
  "serving_image": "operator-supplied-image-digest",
  "ray_version": "operator-supplied",
  "engine_version": "operator-supplied",
  "hardware": "operator-supplied-GPU-and-node-layout",
  "cache_policy": "operator-supplied-warmup-and-cache-policy",
  "generation_settings": {},
  "measurement_policy": {"warmup_seconds": 15, "request_timeout_seconds": 120},
  "required_gates": ["p95_ttft_ms", "p95_itl_ms", "p95_e2e_ms"],
  "quality_kind": "synthetic_correctness_smoke"
}
```

Use real values; the example is not a runnable system configuration. Keep candidate
knobs and config hash in the trial ledger, not in this invariant context. Populate
required_gates with the agreed performance gates. Empty means those SLOs are not
enforced; report this explicitly. Quality smoke is narrow, so task-specific quality
or multi-turn/tool tests may also be required for the intended production claim.

For every trial record: ID, parent/incumbent, exact diff/hypothesis, config hash,
plan/apply/rollback artifacts, measurement windows, per-profile run artifacts,
observer report, validity/reasons, comparison decision, repeat evidence, time/load
consumed and deployed state after the trial. Never overwrite prior trial evidence.

## Comparison and convergence

Use [compare_runs.py](../scripts/compare_runs.py) to screen matching completed runs.
From the optimization directory:

```bash
python3 scripts/compare_runs.py --baseline /private/runs/baseline-short \
  --candidate /private/runs/candidate-short --min-improvement 0.03 \
  --max-throughput-regression 0 --output /private/decisions/trial-01.json
```

Repeat paired `--baseline` and `--candidate` arguments for multiple profiles, in
the same order. The tool requires matching runner manifests and invariant context,
PASS live-run/performance/quality artifacts, required gates configured and passing,
and VALID observation reports with `window_validity: "VALID"`. It screens aggregate
output tokens/s separately per stage. No stage may lose beyond allowed regression,
and at least one must improve by the minimum. Decision is ACCEPTABLE_FOR_CONFIRMATION,
REJECT or INCONCLUSIVE; it does not deploy, prove causality, or certify convergence.
Observation reports are agent-authored evidence assessments, not cryptographic proof.

The agent separately reviews latency/quality tradeoffs, actual output lengths,
artifact windows and the trial diff. Compare repeat distributions/medians within
each profile/stage; don't average percentiles across stages. Bracket a finalist
with repeated incumbent/baseline measurements to reveal drift. Count only valid
comparable non-improvements toward plateau; always count attempted trials toward
the total budget. On budget exhaustion without sufficient repeats, state uncertainty.

## Backend boundary

An additional system such as NVIDIA Dynamo must provide discovery, full config
snapshot, scoped candidate validation, serialized apply/readiness, rollback,
metric/log mapping, and version/resource fingerprint. Reuse OpenAI-compatible
endpoint tests when valid; do not route another control plane through Ray PUT.
The observation and evaluation contracts stay stable while the control adapter
changes. No Dynamo implementation or cross-backend equivalence is claimed today.
