# Proposal: Billing, token metering, and Stripe (USD)

## Problem

SecManus has no product-level **usage metering**, **plans**, or **payments**. `/analyze` historically allowed unauthenticated access and does not enforce quotas. LLM costs are not attributed per user. There is no **Billing** or **Usage** experience aligned with commercial operation.

## Goals

1. **Stripe (USD)** for real payments: **Free** (auto on registration), **Pro ($40/mo)**, **Ultra ($100/mo)**, **Enterprise** (contact sales — no self-serve checkout in app).
2. **Token entitlements**: **Ultra monthly included tokens = 3× Pro** (same unit). Free tier **included tokens** are **configurable** (env or DB seed).
3. **Metering**: Every **LLM** call (main + all sub-agents) records **input** and **output** tokens; **USD cost** from an internal **per-model** table ($/million in/out). **VirusTotal, Tavily, and other non-LLM calls are not billed** to the user.
4. **User controls**: **Monthly spend cap in USD** (ceiling, e.g. max $100) so usage may continue past included allowance until cap; **small arrears** policy per `design.md`.
5. **Gating**: **Only authenticated users** may call `/analyze`. **Quota/billing check once at request start**; **no mid-stream termination** of an accepted analysis.
6. **UX**: **Billing** page (card layout: current plan, balance/credits narrative, payment method, portal/invoices) and **Usage** page (monthly cost by model chart, per-call history with tokens and USD).

## Non-goals

- **Admin UI** this phase (ops: Stripe Dashboard, SQL, scripts).
- Billing third-party APIs (explicitly excluded).
- Currencies other than **USD**.

## Users

- **Subscribers** managing plan, card, caps, and viewing usage.
- **Operators** configuring Stripe, prices, model table, Enterprise flags.

## Scope

| In scope | Out of scope |
|----------|----------------|
| DB schema + RLS for plans, subscriptions, usage, user billing settings | Admin dashboard |
| FastAPI: auth-only `/analyze`, start-of-request billing gate, async usage persistence | Anonymous analyze |
| Stripe Checkout, Customer Portal, webhooks | Multi-currency |
| Model pricing config + usage events | VT/Tavily chargeback |
| React routes + i18n for Billing / Usage | Full marketing pricing site |

## Dependencies

- Stripe **Products/Prices** (Pro, Ultra monthly USD).
- Supabase migrations + RLS (or equivalent local PG).
- Existing JWT auth stack.

## Success metrics

- Paid upgrade path works; Billing shows plan and portal access.
- Usage page shows **per-model** breakdown and **line-item** history.
- Unauthenticated `/analyze` returns **401**; blocked-by-policy returns stable **error codes** for UI.

## Resolved decisions (Phase 1)

- Included allowance: **token count** per period; Ultra = **3×** Pro.
- Spend cap: **USD**; user-editable within a documented max.
- **No** anonymous `/analyze`.
- Reference screenshots: **Mockups deferred** until copied into `mockups/` (see `acceptance-ui.md`).

## Related

- [design.md](./design.md)
- [acceptance.md](./acceptance.md)
- [acceptance-ui.md](./acceptance-ui.md)
