# Publication draft — review and test before publishing

## 1/6

I turned a handwritten LLM load-test sketch into a reusable skill. It uses GuideLLM 0.8.0, the latest release I checked, pinned for repeatable runs. The goal: make a mixed workload easy to describe, run, and inspect.

## 2/6

The mix keeps prompt and output sizes paired, with request weights of 15/15/30/35/5%. Token targets are explicit assumptions: prompts 5k/20k/50k/50k/100k; outputs 256/2048/512/2048/2048. They're configurable, not measurements from production traffic.

## 3/6

The default run has two sequential stages: 12 concurrent streams, then 24. Each stage uses the same workload mix. That lets me compare latency and throughput as concurrency changes without quietly changing the request sizes too.

## 4/6

Setup is Docker plus a .env file: endpoint, model, tokenizer, images, resources, and evaluation thresholds. An optional Ray helper separates the deployment plan from applying it. The load test can also run against an existing endpoint.

## 5/6

Validation so far: 23 unit tests passed. The official GuideLLM Docker image also completed a local mock run: 20 requests in each of two concurrency profiles. That checks the wiring and report path; I don't have real deployment results yet.

## 6/6

Next I'll review the assumptions and test against a real endpoint before publishing results. I'll check the achieved token lengths, errors, p95 time to first token, and inter-token latency. Synthetic load is useful only if I stay clear about what it represents.
