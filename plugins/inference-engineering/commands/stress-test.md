---
description: Run a reproducible stress test against an OpenAI-compatible inference endpoint
argument-hint: endpoint, model, tokenizer and profile settings
---

Load the installed inference-stress-testing skill and follow its plan, probe,
warmup, benchmark and evaluation workflow. User inputs: $ARGUMENTS.
Use writable working copies of the bundled skill folders when the plugin cache
is read-only. Do not tune Ray as part of a benchmark-only request.
Return actual requests, errors, latency/throughput and missing gates with artifacts.
