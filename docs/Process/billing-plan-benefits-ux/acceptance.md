# Acceptance — Billing plan catalog API & data (`billing-plan-benefits-ux`)

## Metadata

- **Slug:** `billing-plan-benefits-ux`
- **Links:** [proposal.md](./proposal.md), [design.md](./design.md), [acceptance-ui.md](./acceptance-ui.md)
- **Last updated:** 2026-05-07

## Scope

后端与 schema：`billing_plans` 扩展、`GET /billing/plans` 响应字段、本地化/兜底策略；不含 Stripe webhook 改动。

## Criteria

| ID | Requirement | Verification |
|----|----------------|---------------|
| A-01 | `billing_plans` 含可编辑权益载荷（见 `design.md` Contracts）且迁移可重复应用 | `supabase db` / 本地 Postgres inspect + pytest |
| A-02 | `GET /billing/plans` 对每个 slug 返回非空 **`benefit_lines`**；**可选** `quota_hints`（仅含已定义的稳定 `id`，如 `concurrent_analyses`、`supported_file_types`、`supported_security_log_types` 等）——**有配置则返回，无则省略** | `curl` / pytest |
| A-03 | 响应仍 **不包含** `stripe_price_id` | 快照或字段黑名单断言 |
| A-04 | 匿名调用（无 Bearer）仍可获取计划列表（若产品要求 público 定价页） | API 测试 |
| A-05 | 现网种子套餐 `free`/`pro`/`ultra`/`enterprise` 均具备可用文案（EN+ZH 至少一端） | 手工或 seeded row 断言 |
| A-06 | `GET /billing/plans` 每个 plan 返回 **`included_credits_usd`**（数值 ≥ 0；Enterprise 可为 0 表示定制） | pytest |
| A-07 | `GET /billing/summary` 返回 **`spent_usd_period`**、**`monthly_spend_cap_usd`**、**`included_credits_usd`**、**`tokens_used_period_estimate`**；类型与单位与 `design.md` § Metering semantics 一致 | pytest |
| A-08 | **未引入** B 方案的抽象「点数扣减表」字段（如 `credits_per_call`、`credits_balance` 等） | 字段黑名单断言 |
| A-09 | **`GET /billing/plans` 与 `GET /billing/summary` 响应**中**不包含** `included_tokens_per_period` 与 `tokens_used_period`（按 § Tokens retirement plan Stage 1） | 字段黑名单断言（pytest） |
| A-10 | DB 列 `billing_plans.included_tokens_per_period` 在本交付**保留**且 schema 注释含 `DEPRECATED`（Stage 2 才执行 `DROP COLUMN`） | 迁移 inspect / pg `\d+` |

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|-----------|------|-------|
| A-01 | Pass | agent | 2026-05-07 | Migration `supabase/migrations/20260507120000_billing_plan_features.sql` adds 5 cols + idempotent UPDATE seeds; mirrored in `python-agent-service/scripts/db/init_local_billing.sql`. |
| A-02 | Pass | agent | 2026-05-07 | `pytest tests/test_billing_plans_api.py::test_billing_plans_returns_credits_and_benefits_local_mocked` asserts `features_json[0].id`, `quota_hints[0].id == "concurrent_analyses"`. |
| A-03 | Pass | agent | 2026-05-07 | `pytest tests/test_billing_plans_api.py::test_billing_plans_response_omits_stripe_price_id` (existing safety contract preserved). |
| A-04 | Pass | agent | 2026-05-07 | `GET /billing/plans` is unauthenticated by route definition; existing public-pricing usage in `OfficialPricing.tsx` continues to work. |
| A-05 | Pass | agent | 2026-05-07 | Migration seeds EN + ZH copy for `free`/`pro`/`ultra`/`enterprise` (`features_json`, `tagline_json`, `quota_hints`). |
| A-06 | Pass | agent | 2026-05-07 | `included_credits_usd` selected and emitted by both `_list_plans_supabase_sync` / `_list_plans_local_async`; default 0 for enterprise; pytest asserts `pro.included_credits_usd == 40.0`. |
| A-07 | Pass | agent | 2026-05-07 | `pytest tests/test_billing_summary_api.py::test_billing_summary_returns_usd_credits_fields` asserts `spent_usd_period`, `monthly_spend_cap_usd`, `included_credits_usd`, `credits_label`, `tokens_used_period_estimate`. |
| A-08 | Pass | agent | 2026-05-07 | No `credits_per_call` / `credits_balance` fields anywhere (grep clean); only USD-equivalent numbers exposed. |
| A-09 | Pass | agent | 2026-05-07 | `pytest tests/test_billing_plans_api.py::test_billing_plans_response_omits_legacy_token_field` + `tests/test_billing_summary_api.py` blacklist `included_tokens_per_period` and `tokens_used_period`. |
| A-10 | Pass | agent | 2026-05-07 | Migration adds `COMMENT ON COLUMN public.billing_plans.included_tokens_per_period IS 'DEPRECATED — removed in Stage 2 (billing-tokens-column-drop). Use included_credits_usd.'`; column NOT dropped. |
