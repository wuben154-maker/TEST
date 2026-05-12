# Project Skill Config

Shared configuration read by all `.cursor/skills/` that need project-level values.
**Edit this file only** — skills reference it and do not maintain their own copies.

---

## Git Workflow

| Key | Value | Notes |
|-----|-------|-------|
| `PR_BASE` | `dev-for-master` | PR target integration branch. Change to `main`, `dev-for-master`, `release/x`, etc. |

---

## Test

| Key | Value | Notes |
|-----|-------|-------|
| `TEST_CMD` | _(unset)_ | Command to run project tests, e.g. `npm test`, `pytest`, `go test ./...`. Set to enable auto-test in `pre-pr-sync` Step 3. |
