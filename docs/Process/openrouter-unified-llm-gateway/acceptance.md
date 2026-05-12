## Metadata

- slug: openrouter-unified-llm-gateway
- owner: product/engineering
- last updated: 2026-04-25
- proposal: `proposal.md`
- design: `design.md`

## Scope reference

This document covers non-UI acceptance for:

- `design.md` > `## Contracts`
- `design.md` > `## Runtime adapter`
- `design.md` > `## OpenCode screening`
- `design.md` > `## Testing strategy`

## Environment

- Local Python agent service.
- Environment variables are loaded from `python-agent-service/.env` or process env.
- No real OpenRouter request is required for automated acceptance; tests may instantiate the LangChain model adapter without invoking the network.
- Secrets must not be written to docs or committed files.

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | Given `OPENROUTER_API_KEY` is set, when the model registry lists models, then configured `openrouter/*` models are included. | Unit test with isolated YAML/env fixture. |
| A-02 | Given `OPENROUTER_API_KEY` is absent, when the model registry lists models, then OpenRouter models are hidden without errors. | Unit test with env key removed. |
| A-03 | Given an explicit `openrouter/*` model id, when `get_model()` is called, then it creates a `ChatOpenAI` model using `https://openrouter.ai/api/v1` and the configured provider-native `sdk_model`. | Factory unit test. |
| A-04 | Given OpenCode and OpenRouter keys are both configured, when `/api/models` is called, then both `opencode` and `openrouter` provider entries can be present. | API or registry integration test. |
| A-05 | Given OpenCode must be hidden later, when the `opencode` provider is removed/commented from `llm_gateway.yaml` or its key is absent, then OpenRouter remains available independently. | Registry test or documented manual check. |
| A-06 | Given OpenRouter models are configured, when `/api/models` returns them, then each item includes `id`, `name`, `provider`, `context_window`, and `max_output_tokens`. | Existing `/api/models` structure test extended for OpenRouter. |
| A-07 | Given OpenRouter is added, existing direct provider and OpenCode gateway tests still pass. | `python -m pytest tests/test_llm_gateway.py` exits 0. |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | OpenRouter support must not introduce a new SDK dependency. | Dependency diff or code review confirms `ChatOpenAI` path is reused. |
| N-02 | OpenRouter attribution headers are optional and must not block requests when unset. | Factory test covers absent attribution env vars. |
| N-03 | Billing must keep OpenRouter usage distinguishable from direct provider usage by using gateway ids with `openrouter/` prefix. | Test or code review of request-scoped model id + pricing seed rows. |
| N-04 | No secret values are committed. | Git diff and staged diff inspection before commit. |

## Evidence

| Criterion | Evidence required |
|-----------|-------------------|
| A-01 | Passing unit test name and command output summary. |
| A-02 | Passing unit test name and command output summary. |
| A-03 | Passing factory unit test name and assertion summary. |
| A-04 | Passing integration/API test or manual `/api/models` response summary with no secrets. |
| A-05 | Passing registry fallback test or documented manual config check. |
| A-06 | Passing `/api/models` structure test. |
| A-07 | `python -m pytest tests/test_llm_gateway.py` exit 0. |
| N-01 | Diff summary showing no dependency file changes, or explicit rationale if dependency changes. |
| N-02 | Passing factory test with attribution env vars unset. |
| N-03 | Pricing seed/code review evidence for `openrouter/*` ids. |
| N-04 | `git diff --cached` inspection before commit. |

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| A-01 | Pass | Agent | 2026-04-25 | `test_registry_supports_openrouter_provider`; `python -m pytest tests/test_llm_gateway.py -q` passed. |
| A-02 | Pass | Agent | 2026-04-25 | Existing registry no-key filtering plus OpenRouter fixture coverage passed. |
| A-03 | Pass | Agent | 2026-04-25 | `test_factory_openrouter_provider_uses_chat_openai` passed. |
| A-04 | Pass | Agent | 2026-04-25 | `openrouter-unified-llm-gateway.noauth.spec.ts` mocked `/api/models` with both providers and passed. |
| A-05 | Pass | Agent | 2026-04-25 | Registry fixture confirmed OpenRouter remains available while OpenCode key is absent. |
| A-06 | Pass | Agent | 2026-04-25 | Real config + `/api/models` structure tests passed with context/output limits. |
| A-07 | Pass | Agent | 2026-04-25 | `python -m pytest tests/test_llm_gateway.py -q`: 30 passed. |
| N-01 | Pass | Agent | 2026-04-25 | Reused `ChatOpenAI`; no dependency file changes. |
| N-02 | Pass | Agent | 2026-04-25 | Attribution headers are optional; tests cover set headers and runtime omits absent headers. |
| N-03 | Pass | Agent | 2026-04-25 | Config and pricing seed use `openrouter/*` gateway ids. |
| N-04 | Pass | Agent | 2026-04-25 | No secret files edited or staged by this workflow. |
