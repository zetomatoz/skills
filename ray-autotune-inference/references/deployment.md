# Deployment mechanics

## Native Python control

Use [ray_control.py](../scripts/ray_control.py) for direct, operator-owned Ray
Serve deployments. It shares the companion skill's tested REST transport and
full-config verification. Python's standard library suffices; no local Ray package
is needed. Export `RAY_DASHBOARD_URL` and optionally `RAY_AUTH_TOKEN` in the shell;
these tools do not automatically load `.env`. Run from this skill's directory:

```bash
python3 scripts/ray_control.py status --output artifacts/status-01
python3 scripts/ray_control.py plan --source /private/path/serve.json \
  --candidate /private/path/candidate.json --app llm --output artifacts/plan-01
python3 scripts/ray_control.py apply --plan artifacts/plan-01/plan.json \
  --output artifacts/apply-01 --timeout 900
python3 scripts/ray_control.py rollback --plan artifacts/plan-01/plan.json \
  --output artifacts/rollback-01 --timeout 900
```

Plan saves original, candidate, and observed configuration together in mode-0600
`plan.json`. Status stores raw state privately. Apply checks the dashboard URL,
source/live match, and saved state, then submits the exact saved candidate. Rollback
requires live submitted configs still match the candidate, preserving unrelated
apps and rejecting intervening changes. Both save private before/submitted/ready
artifacts. A failed PUT or readiness check needs status inspection: rollback is
explicit, never automatic. If PUT was rejected and original remains live, no
restoration is needed. Use fresh output directories to avoid overwriting evidence.

Candidates preserve globals, application sets, unrelated apps, target app
identity/route/runtime/scaling ownership, and explicit deployment identities.
The tool checks selected effective Ray settings and all target-app deployments'
health, positive target counts, and RUNNING replicas. An app scaled to zero must
be brought into a measurable state through its owning scaler first. Confirm
engine arguments in engine logs/telemetry and probe the endpoint separately.
This is not a GPU-budget or engine-schema validator.

For offline plan, add `--state-file /private/path/state.json`. Offline plans cannot
be applied; create a fresh live plan. Ray has no atomic compare-and-swap PUT, so
the final preflight cannot prevent a write racing immediately afterwards. Use one
configuration writer. Globals absent from GET rely on the authoritative source
and writer discipline; they cannot be independently checked from that API.

## Offline engine config edits

Use [mutate_config.py](../scripts/mutate_config.py) to replace existing fields
through explicit JSON pointers. Supply a private changes JSON such as:

```json
{"/applications/0/args/engine/max_num_seqs": 12}
```

This example applies only if your actual config has that path. Inspect the
configuration first; array indices must identify the chosen app and deployment.
Pointers address existing app `args` or deployment fields. Add absent fields
manually to a complete candidate and review against its schema. Escaped keys use
`~1` for slash and `~0` for tilde.

```bash
python3 scripts/mutate_config.py --source /private/path/serve.json \
  --changes /private/path/changes.json --app llm \
  --output /private/path/candidate.json
```

This performs no network calls, preserves unrelated apps and globals, refuses
identity changes and existing output files, and writes mode 0600. Inspect the full
diff before a live plan. It does not infer TP, memory budgets, model compatibility,
or whether a nested value is a tuning knob.

## Use the existing Ray helper for its supported controls

The companion [Ray helper](../../inference-stress-testing/scripts/ray_tune.py)
supports replica count, ongoing requests, and actor CPU/GPU reservations. From
the inference-stress-testing directory, configure its `.env` using the companion
[guide](../../inference-stress-testing/README.md) and [environment example](../../inference-stress-testing/.env.example).

Required: `RAY_DASHBOARD_URL`, `RAY_APP_NAME`, `RAY_DEPLOYMENT_NAME`, and
`RAY_SERVE_CONFIG` pointing to the complete current multi-application JSON config.
Use `RAY_AUTH_TOKEN` only when required by the dashboard gateway. Set just the
intended overrides: `RAY_NUM_REPLICAS`, `RAY_MAX_ONGOING_REQUESTS`, `RAY_NUM_CPUS`,
or `RAY_NUM_GPUS`. Unset stale overrides from previous experiments.

```bash
# From inference-stress-testing; use new output directories for every command.
docker compose run --rm ray plan --output artifacts/ray-plan-01
# Inspect the private original.json and proposed.json before applying.
docker compose run --rm ray apply --output artifacts/ray-apply-01
# Invoke the companion skill's full probe/warmup/load/evaluation workflow.
docker compose run --rm runner run
```

Apply computes a new proposal from current inputs, rather than loading the earlier
plan directory: keep the same inputs and inspect its saved proposal too. The helper
compares source applications with live submitted configs, preserves effective actor
options, checks for concurrent changes, then waits for the requested live settings.
An offline `--state-file` is supported only for plan; it is not live verification.
Static replica overrides clear autoscaling configuration. An external scaler blocks
replica overrides. Make scaling mode changes explicit in the trial description.

## Engine, routing, and topology experiments

The helper does not change engine arguments, placement groups, routing policies,
or images. Inspect the deployment's actual full config and its versioned schema.
Map the desired engine knob to the existing app arguments or deployment code;
do not invent a universal JSON path. Keep router settings at their actual owner,
separate from vLLM engine arguments. Apply through the owning platform or its
supported Serve deployment mechanism and retain a full before/after diff.

For direct Ray ownership, [Serve REST API](https://docs.ray.io/en/latest/serve/api/index.html)
documents GET and PUT `/api/serve/applications/`. GET returns instance details,
not a ready-to-PUT full configuration: use the authoritative deployment file for
global settings and verify each app against its `deployed_app_config`. PUT uses a
complete multi-app configuration and can remove applications omitted from it.
Do not submit a single app fragment to a shared cluster. Validate against the
installed Ray version and confirm all unrelated apps remain present afterwards.

## Platform-owned rollback

Prepare rollback before the first apply. For platform-owned deployments, use the
platform recovery API rather than direct Ray control. The companion helper has no rollback
subcommand and does not accept an arbitrary proposed config differing from live
state. Reapply the saved complete stable config through the owning deployment
mechanism. For direct REST ownership, that means PUT of the saved full config
after checking no unrelated applications changed since the trial. Reconcile
concurrent changes before restoring; never overwrite another operator's work.
Do not translate a platform-specific “delete to restore golden” endpoint into
DELETE on Ray: it can shut down Serve. Verify effective settings, health, replicas,
and endpoint smoke after restoration. Keep TLS verification enabled throughout.
