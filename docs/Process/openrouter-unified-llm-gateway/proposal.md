## Metadata

- slug: openrouter-unified-llm-gateway
- date: 2026-04-25
- tier: Standard
- owner: product/engineering
- related design: `design.md`
- related acceptance: `acceptance.md`, `acceptance-ui.md`

## Problem

SecManus currently supports multiple direct model providers plus OpenCode Zen through `python-agent-service/config/llm_gateway.yaml`. OpenCode is useful for testing but requires provider-specific endpoint handling in `app/llm_gateway/factory.py`. We want OpenRouter available as a unified model transit platform while preserving OpenCode during evaluation.

## Goals

- Add OpenRouter as a first-class LLM gateway provider.
- Keep OpenCode available during the test period.
- Allow future OpenCode removal or hiding through gateway configuration rather than code deletion.
- Preserve the existing `/api/models` and frontend model selector contract.
- Keep billing and context-usage model ids distinct between direct providers, OpenCode, and OpenRouter.

## Non-goals

- Do not remove OpenCode in this delivery.
- Do not migrate every model to OpenRouter immediately.
- Do not add dynamic model discovery from OpenRouter in this delivery.
- Do not change the default model unless explicitly requested.
- Do not introduce a new frontend model-management screen.

## Users

- Analysts choosing models in the workspace composer.
- Developers comparing OpenCode and OpenRouter behavior during model testing.
- Operators managing provider keys and model availability through environment variables and YAML config.

## Scope

- Backend gateway provider registry and factory support for OpenRouter.
- Gateway YAML seed entries for an initial OpenRouter model set.
- Environment variable documentation and `.env.example` placeholders.
- Frontend provider label so OpenRouter models are grouped clearly.
- Regression tests for registry filtering, factory construction, and real YAML model entries.
- Billing seed update or documented zero-cost fallback behavior for new OpenRouter model ids.

## Dependencies

- `langchain-openai` / `ChatOpenAI` remains the runtime adapter for OpenAI-compatible APIs.
- `OPENROUTER_API_KEY` must be configured for OpenRouter models to appear in `/api/models`.
- Optional OpenRouter attribution env vars may be used:
  - `OPENROUTER_APP_URL`
  - `OPENROUTER_APP_TITLE`

## Success metrics

- When `OPENROUTER_API_KEY` is set, `/api/models` includes `openrouter/*` entries.
- When `OPENROUTER_API_KEY` is absent, OpenRouter entries are hidden without errors.
- OpenCode entries remain available when `OPENCODE_ZEN_API_KEY` is set.
- The model selector shows OpenRouter under its own provider group.
- Existing LLM gateway tests remain green.
