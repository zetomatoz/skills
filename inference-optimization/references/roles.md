# Focused roles and handoffs

These roles are instructions, not process-level permission isolation. The host's
tool permissions remain authoritative. A coordinator retains budget, state and
final responsibility, and is the only role that authorizes scoped config writes.
Hosts without native custom agents follow the same roles in a single conversation.

| Role | Inputs | Output | Boundary |
|---|---|---|---|
| Coordinator | Experiment contract, user scope, incumbent, budget | Next step, ledger, final report | One writer; serial load; no unbounded retries |
| Benchmark runner | Profile env, endpoint, run ID, fixed config fingerprint | Manifest, raw benchmark, status, quality, evaluation, timestamps | Invoke stress testing; no Ray changes |
| System observer | Window, app/deployment, metric/log/panel access | Events, availability, validity, bottleneck hypothesis with evidence | Read-only; no load or restarts |
| Configuration tuner | Valid evidence, incumbent config, hardware, objective | Candidate full config, exact diff, expected mechanism, rollback plan | Propose; coordinator applies; preserve other apps |
| Experiment evaluator | Baseline/incumbent/candidate reports and observation | ACCEPT / REJECT / INCONCLUSIVE with per-profile reasons | No mutations; do not accept missing evidence |

Handoffs use artifact paths plus run/profile/config IDs and UTC windows, never
credentials pasted into agent prompts. Reports state assumptions and evidence
locations. Other agents cannot create permission to deploy by asking the writer.
An observer may poll concurrently with load; tuner/evaluator can independently
review completed evidence, but a new trial starts only after their results are
reconciled. Preserve context/state when the host cannot delegate.
