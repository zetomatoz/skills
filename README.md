# Agent skills

Reusable skills and supporting tools for inference engineering.

## Available skills

- [Inference stress testing](inference-stress-testing/README.md): reproducible
  GuideLLM mixed-load benchmarks and optional Ray Serve tuning.
  See the [skill instructions](inference-stress-testing/SKILL.md),
  [test specification](inference-stress-testing/references/test-spec.md), and
  [verification evidence](inference-stress-testing/references/validation.md).

Run commands in the skill's directory:

```bash
cd inference-stress-testing
cp .env.example .env
docker compose run --rm runner plan
```

## Repository checks

From the repository root, check Markdown links and static file references:

```bash
python3 scripts/check_links.py
python3 scripts/check_links.py --external
```

The second command also checks public HTTP links with curl. GitHub Actions runs
both checks on pushes and pull requests. Generated artifacts and user-supplied
configuration files are not expected to exist in the repository.
