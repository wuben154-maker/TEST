# UI Acceptance — `billing-token-stripe-usage`

## Metadata

- **Slug:** `billing-token-stripe-usage`
- **Updated:** 2026-04-07
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- **Routes:** Billing page and Usage page (exact paths per implementation, linked from nav/settings).
- **Components:** Plan card, balance/credits section, payment method / portal entry, upgrade CTAs, usage chart, usage history table, analyze error toasts.

## Mockups deferred

Reference screenshots were discussed in conversation (v0-style Billing, Usage dashboard with cost chart + history table) but **no image files** are committed under `mockups/` yet. **User confirmed proceeding Phase 2 without repo mockups.** Phase 6 `/design-review` shall use **live pages** + criteria below; optional pixel comparison after user adds files to `docs/Process/billing-token-stripe-usage/mockups/`.

## Reference assets (`mockups/`)

| File (repo-relative) | Description |
|----------------------|-------------|
| *(none yet)* | Add e.g. `mockups/billing-reference.png`, `mockups/usage-reference.png` when available |

## Visual criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| U-01 | **Billing** page uses **card sections**: current plan (name, price/mo in USD, short description), primary **Upgrade** and secondary **View plans** (or equivalent) | Desktop 1440px snapshot |
| U-02 | Billing shows **period reset** helper text and **included token** usage as **used / included** (or USD-first with token secondary per `design.md`) | Compare to spec |
| U-03 | **Payment method** area shows empty state + **Add card** (opens Stripe portal/flow) when none | Manual |
| U-04 | **Invoices** or **Manage billing** opens Stripe Customer Portal or external dashboard link with clear label | Manual |
| U-05 | **Usage** page: **month** selector and **stacked bar chart** of **USD** by day with **per-model** series | Desktop snapshot |
| U-06 | **Usage history** table columns: time, model, **input** tokens, **output** tokens, **cost (USD)**, project/session link | Row count > 0 in dev with seed |

## Interaction criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| I-01 | Unauthenticated user cannot start analyze from UI (button disabled or redirect); if API returns 401, user sees actionable message | Manual |
| I-02 | Billing gate failure from API shows **toast/banner** with link to Billing/Usage | Manual |
| I-03 | Changing **monthly spend cap** validates max (e.g. 100 USD) with inline error | Manual |
| I-04 | Upgrade flow completes Stripe redirect and returns to app with updated plan visible after webhook (or refresh) | Staging test |

## Responsive

- **375px:** Billing cards stack vertically; chart scrolls or shrinks without horizontal overflow breaking layout.
- **768px / 1024px:** Table readable; chart legend does not obscure bars.

## Accessibility

- Focus order: skip to main, interactive elements keyboard reachable.
- Contrast sufficient for dark theme text on cards (WCAG 2.1 AA target).
- Touch targets ≥ 44px for primary CTAs on mobile where applicable.

## Sign-off

| ID | Result | Verifier | Date | Notes |
|----|--------|----------|------|-------|
| U-01 | | | | |
| I-01 | | | | |
| … | | | | |
