---
name: inference-optimization
description: Orchestrate bounded stress-test, observe, tune and evaluate experiments for a Ray-managed inference system across fixed workload profiles, retain evidence and rollback, and identify the best verified tested configuration.
---

# Optimize inference

Compose independently callable [stress testing](../inference-stress-testing/SKILL.md),
[observation](../inference-observability/SKILL.md), and
[Ray tuning](../ray-autotune-inference/SKILL.md). Install the plugin for all four.
This is agent-guided orchestration supported by Python tools, not an unattended
deployment daemon. Read [experiment contract](references/experiment.md) and
[focused agent roles](references/roles.md) before operating a live system.

## Plan

Establish authorized environment, deployment owner, endpoint/model/tokenizer,
known-good full config and recovery route, hardware/version fingerprint, objective,
SLO/quality gates, fixed test profile suite, and finite trial/time/load budget.
Default search budget: 10 candidates, 3 repeated measurements for a finalist,
3% minimum useful improvement and plateau after 3 comparable non-improving trials.
These are configurable choices, not universal statistical guarantees. Bound total
wall time and stop safely on cancellation. If inputs are missing, finish an offline
plan; do not claim measurements or mutations. Ray is the only implemented backend.

## Run the loop

1. Create private experiment artifacts and an append-only trial ledger as described
   in the contract. Record the full stable config, profile/environment manifests,
   version/hardware fingerprint, metric mapping and starting deployed state.
2. Invoke stress testing for each fixed profile and collect observations during
   the measured windows. Establish valid repeated baselines; resolve baseline
   failures before tuning. Warmup is separate. Keep raw reports and quality results.
3. Ask the observer for a timestamped bottleneck hypothesis. The tuner produces
   one knob change or coherent topology proposal with resource feasibility and
   rejection/rollback conditions. The coordinator checks the diff and scope.
4. The single writer uses the owner API or Ray tool to apply the reviewed saved
   plan, confirms readiness and actual engine settings, then probes the endpoint.
   Deployment failure triggers inspection and authorized rollback, not another trial.
5. Re-run the identical profile suite, observing the same windows. The evaluator
   compares each profile/stage separately against the incumbent and baseline.
   Use the Python comparison tool for throughput screening and the full contract
   for validity, latency, quality and repeatability. Do not pool incompatible runs.
6. Accept only valid, repeatable improvement meeting all required profile gates.
   Keep the best verified tested configuration as incumbent. Restore it after a
   failed or rejected trial; verify restoration before the next load. Count failed
   and invalid trials toward budget; they do not establish a performance plateau.
7. Continue while a supported hypothesis remains and budget allows. Stop on a
   comparable plateau, objective satisfaction, exhausted trial/wall-time budget,
   cancellation, unexpected external config change, or failed recovery. If evidence
   is missing, report INCONCLUSIVE and the best verified state rather than inventing
   convergence. A finite local search does not establish a global optimum.

## Delegation and output

When the host supports subagents and the user permits delegation, the coordinator
may assign narrow benchmark, observer, tuner and evaluator roles. Parallelize
read-only observation with one benchmark, or independent report review; keep all
load stages and config writes serialized. On other hosts execute the same roles
sequentially. Agent files and tools do not grant new deployment authorization.

Deliver comparison tables for every profile/stage, trial ledger, before/after
configs, raw evidence, accepted/rejected hypotheses, missing gates, stopping reason,
and the exact final deployed state. Promote or restore only within the granted
scope. State whether the finalist was repeated, and call it the best verified
tested configuration for this profile suite, hardware and version fingerprint.
