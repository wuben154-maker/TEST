# Acceptance Criteria: HITL Clarify Gate

## Metadata

- **Slug**: `hitl-clarify-gate`
- **Design**: [design.md](./design.md)
- **Scope**: Backend (prompt + schema); no UI changes

## Criteria

| ID | Category | Criterion | Evidence | Sign-off |
|----|----------|-----------|----------|----------|
| AC-01 | Schema | `FieldSpec` model validates `name`, `label`, `param_type`, `required`, `placeholder` correctly | Unit test pass | |
| AC-02 | Schema | `RequestUserInputArgs.fields` accepts `list[FieldSpec]` and remains backward-compatible with `list[dict]` via Pydantic coercion | Unit test pass | |
| AC-03 | Schema | `_request_user_input_impl` serializes `FieldSpec.param_type` (snake_case) to `paramType` (camelCase) in interrupt payload | Unit test pass | |
| AC-04 | Prompt | `clarify_gate.py` exports `CLARIFY_GATE_GUIDE` constant covering: ambiguity analysis framework, kind selection decision tree, question formulation rules, anti-patterns | File exists; content review | |
| AC-05 | Prompt | `CLARIFY_GATE_GUIDE` is conditionally injected into the main agent system prompt only when HITL is enabled (`agent_hitl_enabled and agent_hitl_main_request_user_input_tool`) | Code inspection of `deep_agent.py` | |
| AC-06 | Prompt | `MASTER_AGENT.md` contains Step 0.5 (Clarification Gate) section between Step 0 and Step 1, referencing the appended guide | File content check | |
| AC-07 | Prompt | All 4 sub-agent `AGENT.md` files (email-security, binary-analysis, web-security, soc-alert) contain domain-specific clarification scenario tables with kind mapping | File content check | |
| AC-08 | Regression | Existing `hitl_interrupt_sse` tests pass without modification | `pytest` exit 0 | |
| AC-09 | Regression | Deep Research `clarify_with_user` flow unaffected (existing tests pass) | `pytest test_research_interrupt_propagation.py` exit 0 | |
| AC-10 | Test | Unit tests exist for `FieldSpec` validation + `RequestUserInputArgs` with all 3 kinds (text/choice/form) | `pytest` exit 0 | |
| AC-11 | Test | Unit tests verify interrupt payload correctness for text, choice, and form scenarios | `pytest` exit 0 | |
| AC-12 | Docs | `docs/HUMAN_IN_LOOP.md` updated with clarification guidance architecture description | File content check | |
