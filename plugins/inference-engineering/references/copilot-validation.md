# GitHub Copilot CLI compatibility

Test date: 2026-10-08. Plugin: 0.1.1. Primary harness: GitHub Copilot CLI.

## Verified locally

- GitHub's official `@github/copilot` 1.0.93 was fetched into a temporary directory
  and executed using a separate temporary `COPILOT_HOME` and `COPILOT_CACHE_HOME`.
  The user's normal Copilot configuration was not used or modified.
- `copilot plugin install <built-plugin-path>` exited successfully, reported
  “Installed 4 skills”, and `copilot plugin list --json` showed version 0.1.1 enabled.
- `copilot skill list` discovered the four canonical skills and the four command
  aliases: observe, optimize, stress-test and tune.
- The generated local marketplace was registered with `copilot plugin marketplace
  add <build-root>`; installing `inference-engineering@inference-engineering-local`
  succeeded and enabled the plugin. Discovery again showed all skills and aliases.
- The native help confirms `/agent`, `/skills`, `/plugin`, `--agent` and
  `--plugin-dir` are supported. The five agents are packaged as `.agent.md` files
  in the explicitly declared agent directory; their layout is covered by tests.

No authenticated model session, custom-agent invocation, Ray mutation, inference
load, log retrieval or Grafana visit was performed. Agent picker visibility and
execution remain part of the user's authenticated harness smoke test. Installation
and discovery evidence do not establish live optimization behavior.

## Format and first smoke

The default uses the established Copilot manifest with explicit `skills`,
`commands` and `agents` paths, rather than requiring Agent Plugins schema support.
The optional portable build remains available. Tested compatibility is 1.0.93;
no minimum version or older-release compatibility is claimed.

Load with `copilot --plugin-dir <built-plugin-path>`, inspect `/plugin`, `/skills`
and `/agent`, then request an offline plan before adding live credentials. Confirm
same-name project/personal skills or agents do not shadow this plugin. Inspect
actual slash-command completions in your session before running a live workflow.

Sources: [plugin manifest and loading conventions](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference),
[official CLI installation](https://docs.github.com/en/copilot/get-started/cli-quickstart).
