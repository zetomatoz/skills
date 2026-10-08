---
description: Run a reproducible stress test against an OpenAI-compatible inference endpoint
argument-hint: spec path, run name, target and runtime environment
---

Load the installed inference-stress-testing skill and follow its plan, probe,
warmup, benchmark and evaluation workflow. User inputs: $ARGUMENTS.
Prefer the supplied native GuideLLM JSON/YAML spec via `--spec` and label results
with `--run-name`. Read runtime endpoints, selected credentials and `CERT_FILE`
from the existing environment/.env without displaying secrets. Model/tokenizer
and workload settings belong to the spec. Preserve its parameters.
Use writable working copies of the bundled skill folders when the plugin cache
is read-only. Do not tune Ray as part of a benchmark-only request.
Return actual requests, errors, latency/throughput and missing gates with artifacts.
