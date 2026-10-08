# Mixed inference test specification

Version: 1.0. GuideLLM: 0.8.0. Source: the supplied handwritten sketch.

## Reading of the sketch

UP means user prompt; MO means model output. Five paired size classes have request
weights **15%, 15%, 30%, 35%, 5%**. The first three sum to 60%, the last two to 40%.
The two 15% classes sum to the first 30% bracket; the third accounts for the other
30%. These percentages describe requests, not token volume or occupied streams.

The sketch calls for 12 and 24 streams and mentions sequence/concurrency. Interpret
that as two sequential stages with closed-loop concurrency: at most 12, then 24
requests in flight. Requests in each stage interleave all five workload classes.
No open-loop requests-per-second target is implied. Add `1` to STREAMS for a serial
baseline or `6` for the sketch's optional six-stream medium/large investigation.
The six-stream note and exact S/M/L/XL boundaries are ambiguous, not requirements
silently inferred from the handwriting.

## Concrete defaults (assumptions, not a literal transcription)

| Bucket | Sketch prompt class | Sketch output class | Weight | Prompt tokens | Output cap |
|---|---|---|---:|---:|---:|
| 1 | S/M | S/M | 15% | 5,000 | 256 |
| 2 | S/M | M/L | 15% | 20,000 | 2,048 |
| 3 | M/L | S/M | 30% | 50,000 | 512 |
| 4 | M/L | M/L | 35% | 50,000 | 2,048 |
| 5 | L/XL | M/L | 5% | 100,000 | 2,048 |

The note's approximate 5k–50k span informs the first four defaults. The XL 100k
choice is an explicit extension. Change all five values with PROMPT_TOKENS and
OUTPUT_TOKENS. Matching-tokenizer counts are approximate after decoding, re-encoding,
and chat-template additions. Reserve context headroom and inspect server usage.
Reject any bucket whose prompt + output cap + margin exceeds CONTEXT_TOKENS.

## Execution and evidence

- Synthetic text only; no external corpus or paid data generation is required.
  A matching model tokenizer may need downloading or mounting locally.
- Preserve prompt/output correlation within each bucket. Never independently
  sample prompt and output sizes or run five isolated benchmarks as a substitute
  for the concurrent mixed workload.
- Default: separate 15-second, single-stream warmup, then measured 12/24 stages.
  Warmup results are stored separately and excluded from evaluation.
- Duration and request limits stop each measured stage at the first bound reached.
  Longer context requests can hit the time bound before the request target.
  Actual mix/counts must be interpreted accordingly; percentages are not an
  instantaneous allocation of streams.
- Use streaming chat completions and save JSON/CSV/HTML evidence. Record image,
  GuideLLM version, tokenizer, seed, scenario, limits, and evaluation thresholds.
- Output lengths are requested caps. Early EOS is valid API behavior and changes
  the measured decode workload. Inspect actual usage. Forced-length generation
  via backend-specific ignore_eos is a separate, explicitly configured experiment.

## Evaluations

Each stage must have measured successful requests, valid finite timing/throughput
metrics, at least 100 completed requests by default, and error rate <=0 by default.
Error rate includes errored and incomplete requests. Optional p95 TTFT, ITL,
end-to-end latency, and minimum output tokens/s thresholds are environment values;
unset thresholds are NOT_CONFIGURED, not evidence that a latency SLO passed.
ITL follows GuideLLM's per-request average ITL distribution; it is not a histogram
of every individual token gap. Do not average percentiles across stages.

The separate correctness smoke checks arithmetic, literal extraction, and a short
instruction. It does not measure general model quality, long-context recall, or
production task accuracy. Disable it with QUALITY_EVAL=0 to retain only the API
probe. Performance and correctness results remain separate artifacts.

For deployment experiments: baseline -> one Ray configuration change -> readiness
and inference probe -> identical workload -> compare. Repeat meaningful candidates
at least three times before drawing capacity conclusions. Record cache/prefix-cache
policy, hardware, engine parallelism, model revision, and all resource settings.
