---
name: ray-autotune-inference
description: Tune an existing Ray Serve inference deployment through bounded, measured knob experiments, diagnose bottlenecks, and delegate OpenAI-compatible endpoint load testing to inference-stress-testing.
---

# Ray inference tuning

Use for improving latency, throughput, or capacity of an existing Ray deployment.
This is an agent-directed experiment loop, not the Ray Tune Python optimizer.
Load [inference-stress-testing](../inference-stress-testing/SKILL.md) for workload
generation, endpoint probes, load tests, and evaluation. Install both skills together;
resolve the benchmark skill through the agent's skill registry if folders move.
Do not recreate benchmark specs or a second runner here.

## Establish the experiment

1. Identify the deployment owner and authorized environment, Ray application and
   deployment names, complete current Serve configuration, dashboard access,
   OpenAI-compatible endpoint, model/tokenizer revisions, serving image and
   Ray/engine versions, GPU topology, context requirement, and rollback route.
   A platform controller may own the config: use its API rather than fighting it
   with direct Ray updates. Never print credentials or commit private configs.
2. Record the objective and latency/error/quality constraints. Default to zero
   unexplained errors; unconfigured gates remain unknown. Choose a finite trial
   budget (default at most 10 candidates), readiness timeout, and load duration.
   Tune only within that scope; a request to plan does not authorize deployment.
3. Snapshot the full known-good configuration and live state privately. Current
   does not necessarily mean known-good. Read [deployment mechanics](references/deployment.md)
   before changing settings and [knob selection](references/knobs.md) to choose
   a hypothesis. Verify actual settings, not just accepted config.
4. Invoke inference-stress-testing to plan and run a baseline. Retain its workload,
   seed, tokenizer, generation settings, context, concurrency profiles, cache
   policy, endpoint path, and evaluation gates across candidates. Its default
   12/24-stream synthetic test does not establish multi-turn tool correctness or
   conversation affinity; require a representative workload for those claims.

## Iterate

1. Diagnose with request metrics plus Ray replica/queue/resource state. Select
   one knob per trial, or one coherent topology change with necessary resource
   adjustments. Record the hypothesis, exact diff, expected gain, and rejection
   condition. Do not sweep random settings to conceal infrastructure failures.
2. Create and inspect a complete candidate config, preserving unrelated apps,
   routes, runtime environment, model revision, parsers, and generation settings.
   Check GPU placement and memory feasibility. Ray GPU reservations do not set
   tensor parallelism; Ray queues and engine batching are different controls.
   Use the offline Python config editor for existing engine fields and save a
   live plan with the native control tool; see the deployment guide for commands.
3. Serialize deployment changes. Recheck live state before applying; stop on an
   unexpected concurrent change. Wait for the target app to be RUNNING, deployment
   HEALTHY, and intended replicas RUNNING with effective settings confirmed.
   Then probe the model and run a small streaming smoke test before full load.
   The native Python tool applies the saved candidate and supports explicit
   rollback. Verify effective engine settings separately in logs or telemetry.
4. Invoke inference-stress-testing for the same planned load using a fresh artifact
   directory. Capture timestamps, config diff, replica restarts, per-replica load,
   GPU utilization/memory, queue state, and available cache metrics for that window.
5. Compare completed/attempted requests, aggregate output tokens/s, p50/p95 TTFT,
   end-to-end latency, errors, and quality for each concurrency profile separately.
   Keep raw failures even when classified. Use [diagnosis](references/knobs.md#diagnosis)
   to separate measured facts from suspected causes. A restart, changed workload,
   or infrastructure interruption makes a run unsuitable for ranking; rerun after
   resolving it within the trial budget.
6. Roll back an unhealthy or rejected candidate to the last verified stable full
   config, then verify readiness and smoke again. Stop if rollback fails, readiness
   times out, the budget is exhausted, or a repeatable gain meets the objective.
   Repeat the apparent winner and baseline when needed to check variability.

## Deliver

Provide a comparison table with trial/config change, concurrency, completed and
attempted requests, throughput, p50/p95 TTFT, errors/quality, validity, and artifact
location. Explain the bottleneck, tradeoffs, missing gates, and next hypothesis.
State exactly which config is currently deployed. Recommend a winner; promote it
only if the user's tuning authorization includes that action. If live inputs are
missing, finish the candidate plan and identify what remains unmeasured.
