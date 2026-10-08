# Source verification

Verified against the published GuideLLM 0.8.0 wheel and official release/image on
2026-10-07 (America/Los_Angeles). The latest release URL resolved to v0.8.0.

- [GuideLLM v0.8.0](https://github.com/vllm-project/guidellm/releases/tag/v0.8.0)
- [PyPI package metadata](https://pypi.org/pypi/guidellm/json)
- [Versioned GuideLLM schemas](https://github.com/vllm-project/guidellm/tree/v0.8.0/src/guidellm/schemas)
- [Ray Serve REST API](https://docs.ray.io/en/latest/serve/api/index.html)
- [Ray deployment configuration precedence](https://docs.ray.io/en/latest/serve/configure-serve-deployment.html)
- [Ray Serve in-place updates](https://docs.ray.io/en/latest/serve/advanced-guides/inplace-updates.html)
- [Ray application containers](https://docs.ray.io/en/latest/serve/advanced-guides/multi-app-container.html)
- [Ray LLM configuration](https://docs.ray.io/en/latest/serve/llm/user-guides/configuration.html)

Pulled official multi-platform image digest:
`ghcr.io/vllm-project/guidellm@sha256:34b3e53ed5d26ce768fd04e48cd6852156e1f35b6b9bdeafd0266d44e8c5af34`.
Set GUIDELLM_IMAGE to that digest for stronger reproducibility than a tag.
