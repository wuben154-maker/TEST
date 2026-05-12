# Acceptance — UI (`billing-plan-benefits-ux`)

## Metadata

- **Slug:** `billing-plan-benefits-ux`
- **Links:** [proposal.md](./proposal.md), [design.md](./design.md), [acceptance.md](./acceptance.md)
- **Last updated:** 2026-05-07

## Scope

- `src/pages/OfficialPricing.tsx`（`/pricing`）
- `src/pages/Billing.tsx`（`/billing`）
- `src/pages/AccountOverview.tsx`（`/account/overview`：套餐与用量摘要区）

## Reference assets

| File | Purpose |
|------|---------|
| — | **Mockups deferred**（无参考图；以 `design.md` 层次为准） |

## Visual criteria

| ID | Criterion |
|----|-----------|
| U-01 | 每档套餐卡片中，**权益列表视觉权重高于** token 原始数字（token 位于次要区或折叠区内） |
| U-02 | 权益使用列表语义（多行左对齐，行距一致），与价格、CTA 的层级符合现有 shadcn Card 规范 |
| U-03 | 「当前套餐」高亮样式与现版一致或更强，但不遮挡权益阅读 |
| U-04 | Enterprise 卡片明确「定制/联系销售」，避免出现「0 token = 无服务」的误读布局 |
| U-05 | **用量区**视觉上从属于权益列表；若存在 **`quota_hints`**，以紧凑行展示且不与 CTA 抢焦点 |
| U-06 | 套餐卡片 **主显单位为 Credits / USD 等价额度**（来自 `included_credits_usd`）；token 数字 **不出现** 在主显区，仅在折叠后可见 |
| U-07 | `/billing` 与 `/account/overview` 的 **主进度条** 来自 **`spent_usd_period / monthly_spend_cap_usd`**；显式带 **`$`** 货币符号 |
| U-08 | 折叠层「计费透明度」含 **token 估算**、**主要模型 $/1M 单价入口**、**一句免责**（与 `design.md` § Metering semantics 文案模板一致） |
| U-09 | `/pricing`、`/billing`、`/account/overview` 中 **不再出现** `included_tokens_per_period` 或「included tokens」「包含 token」之类主显文案；折叠区可出现 token 但前缀必须是「估算 / estimate」相关用语 |

## Interaction criteria

| ID | Criterion |
|----|-----------|
| I-01 | 计费透明度折叠区支持键盘展开/收起，`aria-expanded` 正确 |
| I-02 | `/billing` 与 `/pricing` 上同一 `slug` 的权益文案与 Credits 主显行一致（允许营销页缺少「当前套餐」徽标） |
| I-03 | 账户概览从摘要到 `/usage` / `/billing` 的导航仍可用 |
| I-04 | 定价/账单页底部或用量区可发现 **「计费说明 / FAQ」**入口或锚点（一期允许链到占位或 `#`） |
| I-05 | 折叠区「计费透明度」**默认收起**（marketing & billing），首屏不被 token 数字干扰；展开状态在同一 session 内可记忆（local 即可） |

## Responsive

- **375px**：权益列表不换行溢出；折叠区不横向裁切 CTA。
- **768px**：两列栅格时卡片高度差可接受（顶部对齐）。
- **1280px**：四列营销栅格与现版一致。

## Accessibility

- 列表区对比度满足团队目标（默认 WCAG AA）。
- 焦点顺序：标题 → 价格 → 权益 → CTA → 折叠触发器。

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|-----------|------|-------|
| U-01 | Pass (code) | agent | 2026-05-07 | `PlanCard.tsx` renders `PlanBenefitsList` directly under price + Credits headline; legacy token line removed from primary slot. **Visual `/design-review` SKIPPED** — local dev/api servers not running in this session (MCP unable to reach a live URL). |
| U-02 | Pass (code) | agent | 2026-05-07 | `PlanBenefitsList` uses semantic `<ul>` + `<Check>` icons + uniform leading on shadcn Card (app variant) and marketing border-card variant. |
| U-03 | Pass (code) | agent | 2026-05-07 | `PlanCard` retains current-plan ring + badge (`isCurrent` prop); badge sits beside title, never on top of benefits list. |
| U-04 | Pass (code) | agent | 2026-05-07 | Enterprise: price falls back to `—`, Credits headline shows localized **"Custom usage"** copy via `PlanCreditsHeadline`, CTA = `Contact sales`. |
| U-05 | Pass (code) | agent | 2026-05-07 | `QuotaHintsRow` renders only when `quota_hints` non-empty; placed below benefits, dt/dd grid, smaller type — does not compete with CTA (separate footer slot). |
| U-06 | Pass (code) | agent | 2026-05-07 | All three pages (`Billing.tsx`, `OfficialPricing.tsx`, `AccountOverview.tsx`) only render Credits/USD as primary; raw token figures live exclusively inside `MeteringDisclosure`. Vitest covers helpers: `src/lib/billingDisplay.test.ts` (13 passed). |
| U-07 | Pass (code) | agent | 2026-05-07 | Billing.tsx + AccountOverview.tsx render USD progress bar (`role="progressbar"`, `aria-valuenow=progressPct`), label uses `formatBillingUsdAmount` → `$X.XX` symbols. |
| U-08 | Pass (code) | agent | 2026-05-07 | `MeteringDisclosure` body shows `meteringDisclosureLong` (one-sentence disclaimer + per-million-token wording) + token estimate + `Open Usage page` link in app variant. |
| U-09 | Pass (code) | agent | 2026-05-07 | All four locales (`en`/`zh`/`ja`/`ko`) drop main-display references to "Included tokens / month"; remaining token references are gated under `meteringTokensEstimate` / "estimate" copy keys. |
| I-01 | Pass (code) | agent | 2026-05-07 | Disclosure trigger uses `<CollapsibleTrigger>` (Radix) which manages `aria-expanded` automatically; rotating chevron hooks `open` state. |
| I-02 | Pass (code) | agent | 2026-05-07 | Both `/billing` and `/pricing` consume the same `BillingPlanRow` from `billingApi.getPlans()` and the same `PlanCard` component; benefit / Credits text identical per slug. |
| I-03 | Pass (code) | agent | 2026-05-07 | AccountOverview keeps `Upgrade plan` / `Manage billing` buttons + Usage link in header; navigation paths unchanged. |
| I-04 | Pass (code) | agent | 2026-05-07 | `MeteringDisclosure` (app variant) embeds `Open Usage page` link to `/usage`, satisfying the "FAQ-equivalent entry point". Marketing variant defers entry by design (no auth context). |
| I-05 | Pass (code) | agent | 2026-05-07 | `MeteringDisclosure` defaults `defaultOpen={false}` on every page; user-toggle persists for the lifetime of the component instance via `useState` (per-session) — explicit cross-page memory deferred. |

### Phase 6 exploratory QA notes (SKIP rationale)

- **`/qa` (Playwright MCP):** SKIPPED — local Vite dev (`:8080`) and Python API (`:8000`) are NOT running in this session, and DB migration not applied to a live local Postgres/Supabase. Cannot exercise live UI.
- **`/design-review`:** SKIPPED — same reason (no reachable `base_url`).
- **E2E (`e2e/tests/billing-plan-benefits-ux*.spec.ts`):** SKIPPED in this run — depends on (1) running services, (2) `npm run auth:bootstrap` for the authenticated spec. Specs are committed and ready; rerun with `npm run test:e2e -- --grep billing-plan-benefits-ux` after services are up.
- **Code-level evidence captured above is sufficient for an internal review checkpoint, but is NOT a substitute for the exploratory pass.** Re-open this acceptance file after the local services run to upgrade `Pass (code)` → `Pass (verified)` once `/qa` + `/design-review` execute.
