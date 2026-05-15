# ops-check

A concise ops log inspection Skill: orchestration notes, config loading, script execution, and the collaboration contract with `pr-commit-with-review`. Long-running services are out of scope; triggered by GitHub Actions (hosted or self-hosted Runner) or a manual flow inside Cursor.

## When to use

- Scheduled inspection of production or staging logs, classifying errors and routing them accordingly.
- Manually running `/ops-check` or an equivalent in Cursor to pull recent logs for diagnosis only (no external side effects).
- When low-risk issues should go through an autofix PR, and high-risk or indeterminate issues should go through a GitHub Issue, with Feishu cards in sync.

## Three run modes (same script)

```bash
node ops-check/ops-check.mjs run
node ops-check/ops-check.mjs run --dry-run
node ops-check/ops-check.mjs diagnose --since 30m
```

- `run`: Executes per plan (also constrained by `runtime.dryRun` and `effects`). For Actions.
- `run --dry-run`: Prints diagnostics and the action plan only; no PR/Issue creation, no state writes, no Feishu, no call to the review Skill.
- `diagnose --since 30m`: Manual diagnosis over a time window; same as above, **no external side effects whatsoever**.

Default config path: when `--config` is omitted, use `ops-check/config.yaml`; if missing, fall back to `ops-check/config.example.yaml`.

`dry-run` and `runtime.dryRun` in config **combine**: if either means “dry run only”, no external side effects (including Feishu cards for config errors).

## Config and rules

- Project config: copy `ops-check/config.example.yaml` to `ops-check/config.yaml` and adjust per environment.
- Rules: `ops-check/rules.yaml` — known patterns, severity, `autofix` flags, and fix hints.
- Log sources: `logSources[].id` (unique) and `type`: `cloudwatch` | `file` | **`http-json`**. **`http-json`** must use **`url`** or **`urlEnv`** plus optional **`headersEnv`** mapping header names to **environment variable names** whose values must be set at runtime only (never checked into the repo).

### Align CloudWatch with CI/CD env YAML (optional)

To avoid duplicating the same Log Group name in `ops-check/config.yaml` and `.cicd/env/<env>.yaml`, a CloudWatch `logSource` may use the exact token **${from-cicd-env}** (only this string is recognized) for **`region`** and/or entries in **`logGroupNames`**, or set **`logGroupNames: []`**. Resolution runs after config load and before validation: ops-check reads **`.cicd/env/<cicdEnvironment>.yaml`** at the repo root (default **`cicdEnvironment`**: `prod` if omitted; set **`cicdEnvironment`** in config for `staging` / `dev`). It requires **`logging.cloudwatch.enabled: true`** and a non-empty **`logging.cloudwatch.region`** or top-level **`aws.region`**. For **`logging.cloudwatch.log_group`**: if set and non-empty, that value is used; if omitted or empty, ops-check applies the same convention as **`deploy-aws.yml`** (EC2 ssh awslogs): **`/ecs/{repository.name}-{env}`**, with **`repository.name`** read from **`.cicd/project.yaml`** (default **`app`** when missing, matching `project.get("repository", {}).get("name") or "app"`). If `log_group` is empty you must have **`.cicd/project.yaml`** present. Explicit real `region` / `logGroupNames` values behave as before and never touch the CI/CD file. **Top-level `environment`** remains for display only and is not used to pick the env file path.

### cloudwatch 日志源

从 AWS CloudWatch Logs 拉取日志。适用于容器化部署场景，
当 CI/CD 流水线使用 `--log-driver awslogs` 将容器日志推送到 CloudWatch 时，
ops-check 可直接从对应的 Log Group 中读取（实现上通过本地 **`aws logs filter-log-events` CLI**，`validate-config` 仍要求 YAML 中出现 **`region`** 与 **`logGroupNames`**）。

配置示例：

```yaml
logSources:
  - id: app-cloudwatch
    type: cloudwatch
    region: "ap-southeast-1"
    logGroupNames:
      - "/ecs/my-app-prod"
    service: my-app
```

前提条件：

- EC2 实例或 GitHub Actions runner 需要 CloudWatch Logs 读取权限：`logs:FilterLogEvents`、`logs:GetLogEvents`、`logs:DescribeLogGroups`、`logs:DescribeLogStreams`。
- Log Group 名称必须与 CI/CD awslogs 驱动写入的名称一致。
- AWS 凭证通过环境变量 `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION` 提供（CLI 会使用当前进程环境），或通过 IAM 实例角色 / OIDC 等符合 AWS CLI 的配置提供。

- **Test map**: optional `testMapPath` plus optional top-level **`testPolicy`** override. Default example: `ops-check/test-map.example.yaml`. The selector builds **`required`** and **`optional`** command lists; **every `required` command must exit 0** before a template autofix PR is opened.
- **Fix Agent**: optional `fixAgent.enabled`, `simulateRunner`, `configPath` (overlay — **`ops-check/fix-agent.example.yaml`** Cursor CLI, **`fix-agent.claude-code.example.yaml`** Claude Code `claude -p`, **`fix-agent.modelscope.example.yaml`** chat completions via **`lib/fix-chat-api.mjs`**). **`template_patch`** / **`fix_agent_request`** use **`lib/fix-runner.mjs`** worktrees, **`assertBoundedDiffGate`**, **`runTieredVerification`**, then PR. **`runConfiguredFixAgent`** uses **`chatApi`** when set (HTTP); else CLI **`command` / `args`**. **`simulateRunner: true`** skips execution.

## Fingerprint deduplication and GitHub Issue state

- When `GITHUB_TOKEN` / `GITHUB_REPOSITORY` are present, the script **backfills** `issueNumber` and open/closed state per fingerprint using the `**fingerprint**` field in Issue bodies, from Issues filtered by the first label in `issues.labels`, then decides create, update, `reopen`, or skip duplicates.
- Local `runtime.stateFile` is mainly for cursors, PR linkage, missed-detection streaks, and fields not inferrable from Issues alone; state writes still honor `effects` (`run --dry-run` and `diagnose` do not write).

## LLM cost controls

When rules miss, `ops-check/lib/llm-client.mjs` calls OpenAI **only if** `OPENAI_API_KEY` is set. Limits and caching:

- **`autofix.maxLlmCallsPerRun`** (default `3`): ceiling on LLM HTTP calls per process run after same-run dedup and heuristics.
- **`autofix.maxLlmCallsPerDay`** (default `100`): UTC calendar-day cap; counter resets when the UTC date changes.
- **`autofix.llmVerdictTtl`** (duration string, default `24h`): TTL for cross-run reuse of classifications stored under **`llmVerdicts`** in `runtime.stateFile` (fingerprint-keyed metadata only—no raw log lines).
- **Same-run dedup**: repeated fingerprints in one pass reuse the first LLM outcome without another HTTP call.
- **`llmStats`**: included in `run --dry-run` / `diagnose` stdout JSON and appended to new Issue bodies (`### ops-check_llm_stats`) for observability (counts and budgets, not dollar estimates).

**`shouldAskLlm`** may label obvious non-errors without invoking the model (fail-open to LLM if that heuristic throws).

## Autofix / Fix routing (all must align)

Runtime chooses one of **`fixRoute`**: `template_patch`, **`fix_agent_request`**, or **`issue_only`** (`computeFixRoute` + enrichment in script). Roughly:

- **`template_patch`** only for **low** severity template-capable issues, autofix enabled, **no recurrence**, no forbidden domains/globs, and a **non-empty required test plan** (or fallback from `autofix.verificationCommands`).
- **`fix_agent_request`** for medium/low when agent is enabled, required tests exist, template missing or not eligible — bounded runner + Issue on failure (**never merges**).
- **`issue_only`** for critical/high severity, recurrence, forbidden paths/domains (`auth`, `billing`, migrations, infra, secrets, …), or no safe automation path.

Verification: **`runTieredVerification`** (`ops-check/lib/verification-tier.mjs`) runs **every `required`** command (`shell: true`); **any non-zero exits block the PR**. Optional failures are recorded (`tier: required-pass_optional-failed`) but do not alone block merges from an automation standpoint.

Other gates: autofix/recurrence state, **`autofix.forbiddenPaths`**, remote branch **`ops-check/fix-<fp8>`** dedup (`remoteBranchExists` → skip PR).

If no commands resolve for **required**, verification fails → **no autofix PR**.

Otherwise only create or update an Issue where routing demands it.

## Notifications and secrets

- Feishu webhooks are read **only** from environment variables: `FEISHU_WEBHOOK_URL`, `FEISHU_ESCALATION_WEBHOOK_URL` (aligned with `notifications.*Env` keys in config).
- Overdue PR escalation uses only `FEISHU_ESCALATION_WEBHOOK_URL` (if unset, no-op; does not fall back to the main webhook).
- Do not put webhooks, tokens, or secrets into Issue, PR, logs, or Feishu message bodies.
- `owners.default` and `owners.services.<service>.reviewers` feed owner/.reviewer display on Feishu cards (sanitized names and user ids); missing config does not error.

## Contract with `pr-commit-with-review`

After an autofix PR is created, the Agent or operator should call the nearby `pr-commit-with-review` Skill using the **review request block** (fixed format) emitted by the script. The script **never merges PRs itself**.

### Inputs (aggregated by `ops-check`)

- PR URL
- fingerprint
- error summary
- matched rule name (if any)
- severity
- log evidence summary (sanitized)
- autogenerated patch description
- verification commands with exit codes / excerpted results (each command recorded)

### Expected outputs (one of three)

1. `approved_and_merged`: PR reviewed and merged → on later runs the script sees `merged` via the GitHub API, sets `mergedFix` to true, and updates `reviewStatus`; may pair with “fixed”-style Feishu notice (non–dry-run and when allowed, executed by the script’s effects layer).
2. `changes_requested`: PR should not merge → operator records in Issue comments or state; script may mark the same-fingerprint Issue with an autofix-failure path using `autofixFailed` (per repo convention).
3. `pending_or_timeout`: review incomplete or timed out → `reviewStatus` stays pending; per `notifications.escalatePrAfterMinutes`, send one overdue notice via the **escalation webhook** and record `prEscalated`.

(This version does not ship a second auto-review polling CLI; third-party review outcomes are aligned by operator backfill via Issue/state/comments per convention.)

### Fix Request and review artifacts

Issues/PR bodies and mature preview sections in stdout (`OPS_CHECK_MATURE_PREVIEW_*`) may embed `fixRequest` JSON (see `ops-check/fix-request.schema.json`). For `pr-commit-with-review`, use the block between `--- OPS_CHECK_REVIEW_REQUEST_BEGIN ---` and `--- OPS_CHECK_REVIEW_REQUEST_END ---`; never paste tokens into third-party tools.

## Validation vs “mature acceptance”

- **Synthetic checks** (OK for this repo/tooling smoke): `--help`, `validate-config`, `validate-test-map`, `run --dry-run`, non-empty Planner fixture (`ops-check/config.planner-fixture.yaml`), `node --test ops-check/*.test.mjs`. **`echo`-only proofs are not a substitute** for exercising real stacks.
- **Staging / prod acceptance**: configure real `logSources`, run against **actual staging logs** in a workspace that has runnable tests/E2E (e.g. a service repo with Playwright specs). **`validate-test-map` reporting `e2eDiscovery.found: false`** means **no Playwright/Cypress-style configs were discovered in this checkout** — it is **not** evidence that automated E2E passed. Claiming mature E2E closure requires running in a consumer repo and recording artifacts (see **`ops-check-mature-upgrade-acceptance.md`** §五).

Recommended before enabling live `run` in Actions:

```bash
node ops-check/ops-check.mjs validate-config --config ops-check/config.yaml
node ops-check/ops-check.mjs validate-test-map --config ops-check/config.yaml
node ops-check/ops-check.mjs run --dry-run --config ops-check/config.yaml
node ops-check/ops-check.mjs validate-config --config ops-check/config.planner-fixture.yaml
node ops-check/ops-check.mjs run --dry-run --config ops-check/config.planner-fixture.yaml
node --test ops-check/*.test.mjs
```

## Agent operating instructions

1. Read `ops-check/config.yaml` (or example), **`testMapPath`** / `test-map`, `ops-check/rules.yaml`, and optional **`fix-agent.example.yaml`** overlay.
2. Local diagnose: `node ops-check/ops-check.mjs diagnose --since 30m --config ops-check/config.yaml`
3. **`run --dry-run`** mirrors the planner (sandbox: no Issue/PR/Feishu/state writes).
4. **GitHub Actions**: workflow uses **`concurrency`** to avoid overlapping runs on the same ref; **`hybrid`** job runs only when repo variable **`ENABLE_OPS_CHECK_SELF_HOSTED`** is `true`.
5. Autofix merge path: operator runs `pr-commit-with-review` **only after** an open PR exists; ops-check never merges.
6. **Routing advisor** (`ops-check/lib/route-advisor.mjs`): optional second LLM pass **after** `computeFixRoute` produced `template_patch` or `fix_agent_request`. **Default off** (`routingAdvisor.enabled`); **downgrade-only** (veto / low confidence / parse or HTTP failure → `issue_only`, never upgrade). `dry-run` / `diagnose` skip advisor HTTP unless `--enable-advisor`. User message is `JSON.stringify` of whitelisted payload only (no raw log body). See `config.example.yaml` (`routingAdvisor` block), top-level `routingAdvisorStats`, Issue/PR `advisor:` footer line, optional `state.advisorVerdicts`.

## Design constraints

- The Skill only handles orchestration and contracts; the **sole execution entrypoint** is `ops-check/ops-check.mjs`.
- Merging multiple log sources, `fingerprint` dedup, recovery close, and relapse escalation follow the design doc and script; `diagnose --since` uses one time window for all sources; plain `run` computes `since` per log source.
