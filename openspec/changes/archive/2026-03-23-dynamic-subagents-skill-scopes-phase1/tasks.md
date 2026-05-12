## 1. Registry and bundle layout



- [x] 1.1 Add `subagents.registry.yaml` schema v2: `defaults.bundles_root`, `subagents[].id`, `enabled`, `source` (`official` only enforced in Phase 1), `bundle_path`, `description`, `routing_hints`, `tool_profile`, `extra_skill_package_ids`, `include_shared_skills`, `runtime`; validate with Pydantic (or equivalent).

- [x] 1.2 Create **`subagents/official/<id>/`** layout for each Phase 1 subagent: **`AGENT.md`** (system prompt body) + **`skills/`** (child packages with `SKILL.md` + optional `skill.config.yaml`); migrate or symlink from legacy `python-agent-service/skills/<id>` where needed, or use `extra_skill_package_ids` until bundles are populated.

- [x] 1.3 Implement registry loader: filter `enabled: true` + `source: official` → resolve `bundle_path` → verify required files → build `SubAgentSpec` (paths to prompt file, skill roots, tool profile, runtime).

- [x] 1.4 Implement loader for optional per-skill **`skill.config.yaml`** under **global** `skills/` and under **bundle `skills/`** (same rules); merge into package records.

- [x] 1.5 Implement `SkillSource` protocol: `list_official()` from global discovery + config; `list_for_tenant` stub `[]` for Phase 2.



## 2. Wire create_deep_agent and task catalog



- [x] 2.1 For each `SubAgentSpec`, set `system_prompt` from bundle **`AGENT.md`**; set SkillsMiddleware `skills` sources to **bundle `skills/`** roots + resolved `extra_skill_package_ids` + shared bucket when `include_shared_skills`.

- [x] 2.2 Map `tool_profile` to `TOOL_PROFILES[profile_id]` (replace `get_tools_for_agent` elif growth over time).

- [x] 2.3 Implement **`COMPILED_SUBAGENT_BUILDERS`** (or equivalent) keyed by registry `id`; wire `runtime: compiled` to the factory (e.g. `build_open_deep_research_compiled_subagent`), passing resolved bundle path + registry metadata + skill roots per `design.md` D11; validate at startup that every compiled registry id has a builder.

- [x] 2.4 Build `available_agents` / `TASK_TOOL_DESCRIPTION` fragment **only** from registry snapshot (descriptions + routing_hints); keep single source of truth vs `AGENT.md`.



## 3. Guards and future user source



- [x] 3.1 If registry contains `source: user`, **omit or fail** per policy (document default: omit with warning log).

- [x] 3.2 Document reserved layout for future **`subagents/user/`** (same D10 structure) in README; no runtime scan in Phase 1.



## 4. Prompts and docs



- [x] 4.1 Update `MASTER_AGENT.md`: subagents come from registry + bundles under `subagents/official/`.

- [x] 4.2 Update `project_context.md` after implementation.

- [x] 4.3 Document **config refresh** (D9): registry vs bundle `AGENT.md` vs `skills/` (task 6.3 scope).



## 5. Verification



- [x] 5.1 Unit tests: disabled subagent excluded; `bundle_path` missing → clear error; official-only filter.

- [x] 5.2 Integration smoke: delegate to one migrated subagent; skill progressive disclosure still works from bundle `skills/`.

- [x] 5.3 Rollback: feature flag or legacy `build_subagent_specs` path.


