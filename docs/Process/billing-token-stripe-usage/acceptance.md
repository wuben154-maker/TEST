# Acceptance — `billing-token-stripe-usage`

## Metadata

- **Slug:** `billing-token-stripe-usage`
- **Owner:** (team)
- **Updated:** 2026-04-07
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- Authenticated-only `POST /analyze` and billing **start-of-request** gate
- LLM usage persistence (`llm_usage_events`) and **exclusion** of non-LLM tool costs
- Stripe Checkout, Customer Portal, and **webhook** subscription sync
- REST: billing summary, settings, usage aggregates and event list
- Data model and RLS expectations as described in `design.md` **Contracts**

## Environment

- **Runtime:** Local: Vite + `uvicorn` + Supabase local or staging project
- **Base URL:** `http://localhost:8000` (API), Stripe **test mode** keys
- **Feature flags:** Document `BILLING_ENFORCE` / equivalents in `env.md` when added

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | `POST /analyze` **without** `Authorization: Bearer` returns **401** with stable `error_code` | `curl` / pytest |
| A-02 | `POST /analyze` with valid user but **billing gate deny** returns **402 or 403** with documented `error_code` (e.g. cap exceeded) | pytest with seeded usage + cap |
| A-03 | After gate **allows**, streaming completes without **mid-stream** HTTP termination for billing (same connection until natural done/error) | Manual or integration note in test doc |
| A-04 | Each completed **LLM** call (main or subagent path under test) inserts **one** `llm_usage_events` row with `prompt_tokens`, `completion_tokens`, `model_id`, `cost_usd` | pytest + DB query |
| A-05 | **No** `llm_usage_events` row is created for **VirusTotal** or **Tavily** tool invocations in controlled test | pytest |
| A-06 | `cost_usd` matches formula: `(prompt/1e6)*price_in + (completion/1e6)*price_out` for known `model_pricing` row | Unit test |
| A-07 | `GET /billing/summary` returns plan slug, period bounds, included token usage, period **USD** spend, and **monthly_spend_cap_usd** | `curl` with auth |
| A-08 | `PATCH /billing/settings` rejects `monthly_spend_cap_usd` above server maximum (e.g. 100) | pytest |
| A-09 | Stripe webhook with **invalid** signature returns **400** and does not mutate DB | pytest |
| A-10 | Idempotent replay of same Stripe `event.id` does not duplicate subscription rows | pytest |
| A-11 | New user after registration has **Free** plan (or equivalent) and default billing settings | Integration / SQL check |
| A-12 | `GET /usage/events` supports pagination and returns model + tokens + `cost_usd` + `project_id` when present | pytest or `curl` |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | Stripe **secret** and **webhook secret** never returned in JSON responses | Grep / code review |
| N-02 | Billing tables not readable cross-user under RLS (if client reads) or only server-side with service role | SQL policy test or architecture note |
| N-03 | Webhook handler completes within typical timeout under test payload | Local timing / logs |

## Evidence notes

- A-01: expect `401`, body includes `error_code` per `design.md`
- A-04–A-06: use fixed pricing row and stub LLM response with known usage metadata
- A-09–A-10: Stripe CLI or mocked signed payload fixtures

## Sign-off

| ID | Result | Verifier | Date | Notes |
|----|--------|----------|------|-------|
| A-01 | pass | agent | 2026-04-07 | `pytest tests/test_analyze_requires_auth.py` |
| A-02 | partial | agent | 2026-04-07 | Policy tests `test_billing_gate.py`; DB-seeded HTTP 402/403 E2E not run |
| A-03 | — | | | Stream-interrupt not automated this pass |
| A-04 | partial | agent | 2026-04-07 | Callback + insert path live; no pytest against real LLM row this pass |
| A-05 | — | | | VT/Tavily exclusion test not added |
| A-06 | pass | agent | 2026-04-07 | `pytest tests/test_billing_pricing.py` cost formula |
| A-07 | partial | agent | 2026-04-07 | `GET /billing/summary` implemented; curl with auth not recorded |
| A-08 | pass | agent | 2026-04-07 | `pytest tests/test_billing_webhook.py::test_patch_billing_settings_rejects_over_server_max` |
| A-09 | pass | agent | 2026-04-07 | `test_stripe_webhook_rejects_bad_signature` |
| A-10 | — | | | Idempotency replay test not added |
| A-11 | partial | agent | 2026-04-07 | Bootstrap on register; no integration SQL assert |
| A-12 | partial | agent | 2026-04-07 | `GET /usage/events` implemented; curl not recorded |

**Phase 6 — Browser / Playwright:** `/qa` and `/design-review` **not executed** in this session (Playwright MCP not invoked). Billing/Usage pages verified via Vitest pass + code paths only.
