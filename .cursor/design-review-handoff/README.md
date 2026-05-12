# Design review handoff (local test only)

This folder configures **where** **`/design-review`** and **Playwright MCP** (`/qa`) open the app. It is **not** part of the shipped product and **must not** be published.

## Scope: not duplicate of `.env`

| File | In git? | Used by | Purpose |
|------|---------|---------|---------|
| **Repo root `.env` / `.env.local`** | **No** (gitignored) | Vite, **`npm run auth:bootstrap`** | **`VITE_*`**, API URL, **`E2E_EMAIL` / `E2E_PASSWORD`** (login for local automation). See **`docs/Process/LOCAL_AUTOMATION_AUTH.md`**. |
| **`target.example.yaml`** | **Yes** | Humans | **Template only** — copy to `target.local.yaml`, no secrets. |
| **`target.local.yaml`** | **No** (gitignored) | `/design-review` skill | **Test-only:** `base_url`, `priority_paths`, `mockups:` list. **Do not** put passwords here for SecManus — use root `.env` + **`auth:bootstrap`**. |

**Summary:** One place for **account secrets** → **root `.env`**. One place for **“which URL to audit”** → **`target.local.yaml`** (from **`target.example.yaml`**).

## Lifecycle (upload / release)

- **`target.local.yaml`** — **never commit**, **never** include in production builds or Docker images. **Local + optional CI secret** if you ever inject it in a private pipeline (still not “published” to end users).
- **`target.example.yaml`** — safe in repo; contains **no** secrets, **no** real URLs required (adjust defaults to match your machine).

## Files

| File | Committed? | Purpose |
|------|------------|---------|
| `target.example.yaml` | Yes | Copy to `target.local.yaml`; template for local design-review target. |
| `target.local.yaml` | **No** | Real `base_url` and paths — **local testing only**, gitignored. |

## Setup

1. Copy **`target.example.yaml`** → **`target.local.yaml`** (same directory).
2. Set **`base_url`** to your running Vite app (this repo defaults to **`http://127.0.0.1:8080`** — check `vite.config.ts` `server.port`).
3. **Login for automation:** configure **`E2E_EMAIL` / `E2E_PASSWORD`** in **repo root** **`.env`**, run **`npm run auth:bootstrap`**, then **`browser_navigate`** to the printed URL once in **Playwright MCP** — **`docs/Process/LOCAL_AUTOMATION_AUTH.md`**.
4. **Mockups** live under **`docs/Process/<slug>/mockups/`**; optionally list repo-relative paths under **`mockups:`** here for tooling.

## Auth (`auth:` block)

For SecManus, prefer **`type: none`** plus **`auth:bootstrap`** (credentials in **`.env`** only). The **`auth.username` / `password`** fields exist for other stacks that implement HTTP Basic or form fill; they are **optional** and **not** the recommended place to duplicate `.env` secrets.

## Security

- Treat **`target.local.yaml`** like **`.env`**: do not commit, do not paste into public chats.
- If secrets were ever committed, rotate them and purge git history as needed.
