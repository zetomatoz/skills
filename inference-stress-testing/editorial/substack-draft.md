# From a notebook sketch to a repeatable LLM load test

*Draft for review and testing before publication.*

The starting point was a notebook page: a mix of user-prompt sizes and model-output
sizes, five percentages, and two concurrency levels. The useful next step was to
turn that sketch into an experiment I could reproduce and change through a few
environment variables.

The result is a reusable skill built around GuideLLM, Docker, and synthetic text.
It describes the workload, produces a runnable scenario, optionally tunes an
existing Ray Serve deployment, and checks the resulting measurements.

The implementation pins GuideLLM 0.8.0, the latest stable release verified while
building it. Pinning matters here: the current CLI uses `guidellm run`, and a
repeatable benchmark needs a known configuration and report format.

The workload has five paired buckets:

| Share of requests | Prompt tokens | Requested output cap |
|---:|---:|---:|
| 15% | 5,000 | 256 |
| 15% | 20,000 | 2,048 |
| 30% | 50,000 | 512 |
| 35% | 50,000 | 2,048 |
| 5% | 100,000 | 2,048 |

The percentages come from the sketch. The precise token counts are implementation
assumptions. In particular, 100,000 tokens is an explicit choice for the extra-large
bucket. All five prompt sizes and output caps are configurable, and the runner
checks that each pair fits within the declared context window with some headroom.

Keeping these pairs together is essential. A long prompt followed by a short
answer places different demands on serving than a short prompt followed by a long
answer. Sampling input and output sizes independently would change the experiment.

There is also a useful GuideLLM detail: multiple data sources are combined within
a row; they do not automatically become a weighted mixture. This implementation
therefore creates one small CSV containing paired input/output lengths, in a
seeded order. GuideLLM's synthetic trace loader creates the corresponding text
using the configured tokenizer. No external dataset or LLM-generated test corpus
is needed.

A complete default trace contains 200 requests: 30, 30, 60, 70, and 10 from the
five buckets. The runner measures that workload at 12 concurrent streams and then
24. These are successive closed-loop concurrency targets. The percentages describe
requests; they do not reserve particular streams for particular buckets.

The first practical interface is an environment file:

```dotenv
AI_ENDPOINT=http://host.docker.internal:8000
AI_MODEL=my-served-model
TOKENIZER=my-org/my-model
STREAMS=12,24
MIX_WEIGHTS=15,15,30,35,5
REQUESTS_PER_STAGE=200
DURATION_SECONDS=300
```

The full example also exposes the API key, token sizes, actual context limit,
container images, load-generator resources, Ray settings, and evaluation thresholds.
The matching tokenizer is important: a served-model alias alone does not establish
how the synthetic prompt should be tokenized.

After editing that file, the workflow is small:

```bash
docker compose run --rm runner plan
docker compose run --rm runner run
```

The plan writes the trace, manifest, and scenario without contacting an inference
endpoint. The run performs an API probe, optional simple correctness checks, a
separate warmup, and the measured stages. Each stage stops when its request or time
limit is reached. A time-limited run may therefore measure only part of the intended
mix; its actual request counts belong in the interpretation.

Evaluation happens per stage. The defaults require valid metrics, at least 100
successful measured requests, and zero errored or incomplete requests. Latency and
throughput targets are supplied explicitly. An unset target is recorded as
`NOT_CONFIGURED`; a passing run does not establish a latency SLO that was never set.

There is one distinction I want visible in every result: a requested output length
is a cap. A model can stop early. The report compares requested caps with reported
token usage where available, so an apparently faster configuration is not quietly
credited for doing less decoding. The tiny correctness checks cover arithmetic,
literal extraction, and following a short instruction. They offer no evidence of
general model quality or long-context accuracy.

Ray tuning is an optional separate step. The helper plans and applies changes to
replicas, maximum ongoing requests, and actor CPU/GPU reservations through the
Serve REST API. It requires the complete current configuration, preserves unrelated
applications, checks for stale settings, and waits for readiness. A serving-image
change still belongs in the existing Docker or KubeRay deployment workflow. Actor
resource reservations also do not automatically configure the model's tensor
parallelism.

What has been tested so far is the machinery. The 23 local tests pass. The official
GuideLLM container also completed both configured concurrency profiles against a
local mock endpoint: 20 successful requests per profile, zero errors, and passing
evaluation. That smoke test used tiny prompts and outputs. It verifies the runner
and report processing; it provides no real-model capacity or GPU performance result.

My first deployment experiment will be a baseline, one controlled Ray change, and
the same workload again. I will keep the tokenizer, seed, limits, and cache policy
fixed and repeat promising configurations before drawing conclusions. The skill
makes that experiment easy to reproduce. The real endpoint still has to supply the
evidence.

Sources: [GuideLLM 0.8.0](https://github.com/vllm-project/guidellm/releases/tag/v0.8.0),
[Ray Serve API](https://docs.ray.io/en/latest/serve/api/index.html),
and [Ray deployment configuration](https://docs.ray.io/en/latest/serve/configure-serve-deployment.html).
