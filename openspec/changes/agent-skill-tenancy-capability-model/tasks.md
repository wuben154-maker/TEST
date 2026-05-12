## 1. Schema and registry foundations

- [ ] 1.1 Add `capability_id`, `scope` (main/subagent/global/profile), and optional `precedence` fields to skill manifest convention (SKILL.md frontmatter or `skill.yaml`); document in repo contributor docs.
- [ ] 1.2 Implement a pure function `resolve_effective_skills(tenant_id, policy, candidates)` that applies visibility, D4 precedence, and D2/D3 ordering; unit tests for official+tenant conflicts and same-tier time order.
- [ ] 1.3 Emit structured suppression records (`conflict_suppressed`, winner id, reason) for admin/API consumption (in-memory first if DB not ready).

## 2. Backend integration (python-agent-service)

- [ ] 2.1 Replace ad-hoc discovery-only flow with a registry builder that merges official filesystem skills with tenant skill source (stub or DB) and runs conflict resolution before building SubAgent specs and skill indexes.
- [ ] 2.2 Add settings for `skill_conflict.precedence` (`official_wins` | `tenant_overrides_official`) and max-step/budget guardrails per `agent-orchestration` spec.
- [ ] 2.3 Refactor `get_tools_for_agent` toward capability- or profile-based tool maps consumed by registry (reduce elif growth); keep behavior parity tests for existing agents.
- [ ] 2.4 Align `task` tool / subagent description injection with registry snapshot for the active tenant/session.

## 3. Tenancy and persistence

- [ ] 3.1 Design and migrate Supabase (or chosen store) tables for tenant skills, install records, `installed_at` / monotonic seq, and RLS so other tenants cannot read private packages.
- [ ] 3.2 APIs for upload, marketplace install-to-tenant, list effective vs suppressed skills for tenant admins.
- [ ] 3.3 Wire registry builder to load tenant rows instead of stub when feature flag enabled.

## 4. Streaming and frontend

- [ ] 4.1 Define and document the event envelope (`run_id`, `parent_run_id`, `phase`, `payload`) in code as shared types/constants; map existing SSE events incrementally.
- [ ] 4.2 Extend `useStreamingAnalysis*` and reasoning components to nest child runs under parent when `parent_run_id` is present.
- [ ] 4.3 Add adapter tests or fixtures for compiled-graph streams mapping into unified phases (e.g. deep-research).

## 5. Agent runtime consolidation (later phase)

- [ ] 5.1 Introduce or standardize on `general-purpose` subagent path for domain skills that do not need a compiled graph; migrate one pilot skill end-to-end.
- [ ] 5.2 Update `MASTER_AGENT.md` (or equivalent) routing guidance to match registry-sourced catalog and explicit completion expectations.

## 6. Verification

- [ ] 6.1 Add integration tests: tenant A cannot see tenant B skills; conflict resolution winner/loser; main vs subagent skill scope honored in injected index.
- [ ] 6.2 Manual QA checklist: marketplace install conflict UI, official_wins vs tenant_overrides toggle, stream nesting in reasoning panel.
