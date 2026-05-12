## 1. Spike and contracts

- [x] 1.1 Spike: confirm LangGraph + checkpointer version for `interrupt`, nested subgraph under `task()`, and exact `Command(resume=...)` (or equivalent) shape for main graph and subagent graph
- [x] 1.2 Document chosen resume JSON schema and error codes in `docs/Process/` (short HITL resume appendix or extend `SSE_EVENT_CATALOG.md`)

## 2. Main agent orchestration

- [x] 2.1 Add configurable `interrupt_on` for `create_deep_agent` in `DeepAgentWithIntent._build_official_agent` (settings or module-level map; default safe/off for production)
- [x] 2.2 Implement `POST` resume route (path per design D4) with auth/session ownership checks and pass-through to graph resume
- [x] 2.3 Extend `adapt_astream_to_sse` (or parallel handler) to detect main-graph `HumanInTheLoopMiddleware` interrupt, emit `decision_request` (or agreed type) with `HITLRequest` fields, and terminate SSE in defined `done` / waiting semantics
- [ ] 2.4 Add integration test: main agent proposes gated tool → stream shows review event → resume approve → tool runs

## 3. Subagent interrupt_on (registry)

- [x] 3.1 Extend `SubagentRegistryEntry` and `subagents.registry.yaml` schema with optional `interrupt_on` (validated against known tool names per profile where feasible)
- [x] 3.2 Merge `interrupt_on` in `build_subagent_specs_from_registry` output dicts
- [ ] 3.3 Add integration test: `task()` → subagent proposes `execute` (or chosen tool) → interrupt inside subagent stream → resume → subagent completes → parent `task` returns

## 4. Dedicated `request_user_input` tool (pattern C)

- [x] 4.1 Define TypedDicts (or Pydantic) for `UserInputRequestPayload` / `UserInputResponsePayload` and register tool on subagent tool lists (and optionally main agent behind flag)
- [x] 4.2 Implement tool body: `interrupt(request_payload)`; on resume, return structured tool result to model
- [x] 4.3 Map custom interrupt to SSE: `parameter_request` / `decision_request` with `interruptKind: user_input_v1` and stable `requestId`
- [x] 4.4 Update subagent `AGENT.md` / `MASTER_AGENT.md` guidance: when to use `interrupt_on` vs `request_user_input`
- [ ] 4.5 Add integration test: subagent calls `request_user_input` → SSE → resume → continued reasoning

## 5. Frontend

- [x] 5.1 Extend streaming hooks to detect waiting-for-human state after interrupt (from event payload and/or terminal marker)
- [ ] 5.2 Implement UI for standard tool review (approve/edit/reject) wired to resume API — **partial**: `submitHitlResume(resume)` + `hitlAwaiting` / `hitlSnapshot` exported; product panels should call `submitHitlResume` with LangGraph-shaped `resume` (e.g. `decisions` for HITL middleware)
- [ ] 5.3 Implement UI branches for `interruptKind: user_input_v1` (choice vs form vs text)
- [x] 5.4 Update `src/types/analysis.ts` for new optional fields (forward-compatible)

## 6. Compiled subagent policy

- [x] 6.1 Confirm Phase 1 policy in code or docs: compiled entries ignore registry `interrupt_on` unless builder updated; add warning log or validation if misconfigured
- [ ] 6.2 If (b): inject HITL into `build_open_deep_research_compiled_subagent` (separate follow-up tasks as needed) — **deferred / Phase 2**

## 7. Hardening and docs

- [x] 7.1 Implement concurrent resume / double-analyze policy (409 or equivalent) per `agent-hitl-orchestration` spec — **SSE error events** (`hitl-pending`, `hitl-nothing-pending`) + optional HTTP where applicable
- [ ] 7.2 Optional: timeout or auto-reject stale interrupts (product decision)
- [x] 7.3 Update `project_context.md` with HITL overview and links to new docs
