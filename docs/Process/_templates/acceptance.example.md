# Acceptance — `<requirement-slug>`

## Metadata

- **Slug:** `<requirement-slug>`
- **Owner:** `<name>`
- **Updated:** YYYY-MM-DD
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- `<subsystem or API name>`
- `<data contract or job>`

## Environment

- **Runtime:** e.g. local docker compose / staging
- **Base URL / entrypoint:** e.g. `http://localhost:8000`
- **Feature flags:** none | list

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | e.g. POST /api/foo returns 201 with body schema X | `curl` / test command / script name |
| A-02 | e.g. Idempotent retry does not duplicate rows | SQL query or integration test id |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | e.g. p95 latency under 200ms for endpoint Y at RPS Z | load tool / metric dashboard |
| N-02 | e.g. Unauthorized requests return 401 | automated test id |

## Evidence notes

- A-01: expected JSON keys / status code. **E2E:** `E2E-01` in `e2e/tests/<slug>.spec.ts`.
- A-02: expected row count / invariant. **E2E:** `E2E-02` (or manual verification if not automatable).

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | | e.g. `E2E-01 passed` / `curl` output | | | |
