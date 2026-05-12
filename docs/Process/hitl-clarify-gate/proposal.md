# Proposal: HITL Clarify Gate

## Problem

The current HITL (Human-in-the-Loop) system has an asymmetry:

- **Deep Research** has a robust 3-layer clarification mechanism: dedicated prompt (`clarify_with_user_instructions.md`) → structured output schema (`ClarifyWithUser`) → programmatic interrupt. This ensures the model reliably asks the user when scope is unclear.
- **Main Agent & standard sub-agents** (email-security, binary-analysis, web-security, soc-alert) have only a bare `request_user_input` tool with 3 lines of guidance in their prompts. The model frequently "assumes it can handle it" and skips asking, leading to lower-quality analysis results.

Additionally, the existing `request_user_input` tool supports three interaction kinds (`text`, `choice`, `form`), but the prompts provide zero guidance on **when** to use which kind, or **what scenarios** warrant each type of user interaction.

## Goals

1. **Reliable clarification**: The main agent and sub-agents should consistently ask users for input when information is genuinely insufficient, without requiring a mandatory graph-level gate on every message.
2. **Flexible interaction types**: The model should correctly select `text` (open questions), `choice` (pick from options), or `form` (structured fields like credentials/URLs) based on the scenario.
3. **Zero graph changes**: Achieve this through prompt engineering + schema enhancement only. The existing react agent loop, SSE pipeline, and frontend components remain unchanged.
4. **Domain-aware guidance**: Each sub-agent gets domain-specific clarification scenarios (e.g., email-security knows to ask about missing .eml attachments; binary-analysis knows to ask about target platform).

## Non-goals

- Replacing Deep Research's mandatory `clarify_with_user` node (it stays as-is; its forced checkpoint is appropriate for research scope clarification).
- Adding new graph nodes or changing the agent execution flow.
- Frontend UI changes (all three kinds already render correctly).
- New SSE event types (the existing `parameter_request` / `decision_request` pipeline handles everything).

## Users

- **End users** of SecManus who submit security analysis requests — they get better, more targeted questions when their input is ambiguous.
- **Operators** who configure HITL settings — no new env vars or config needed beyond existing `AGENT_HITL_ENABLED` and `AGENT_HITL_MAIN_REQUEST_USER_INPUT_TOOL`.

## Scope

| In scope | Out of scope |
|----------|-------------|
| `MASTER_AGENT.md` Step 0.5 prompt section | Deep Research `clarify_with_user` node changes |
| `RequestUserInputArgs` schema enhancement (`FieldSpec`) | New graph nodes or middleware |
| Sub-agent `AGENT.md` domain-specific clarification guidance | Frontend component changes |
| Unit tests for schema validation | New SSE event types |
| Documentation update (`HUMAN_IN_LOOP.md`) | New env vars or config keys |

## Dependencies

- Existing `request_user_input` tool (`app/tools/hitl_tools.py`)
- Existing `hitl_interrupt_sse.py` SSE pipeline
- Existing frontend `ParameterInput` / `UserDecision` components

## Success Metrics

1. Model correctly uses `request_user_input` with appropriate `kind` when input is genuinely ambiguous (validated via manual test scenarios).
2. Model does NOT over-ask when information is already sufficient.
3. All three interaction kinds (`text`, `choice`, `form`) produce correct SSE events and frontend rendering (verified by existing test infrastructure).
4. Zero regressions in existing HITL flows (Deep Research clarification, tool-approval `interrupt_on`).
