# Local automated login (dev only)

For **`/qa`** (Playwright MCP), **`/design-review`**, or any browser automation against the **Vite** app, the app at `/` requires `localStorage` keys **`auth_token`** and **`auth_user`** (see `src/lib/api-client.ts`).

**Config split (not duplicate of `target.local.yaml`):** account credentials live in **repo root `.env`** (`E2E_*`). **`target.local.yaml`** (from **`target.example.yaml`**) only tells design-review **which URL** to open — see **`.cursor/design-review-handoff/README.md`**.

## `npm run auth:bootstrap`

1. Start **Python API** (e.g. `uvicorn` on port **8000**).
2. Put credentials in **repo root** **`.env`** or **`.env.local`** (gitignored patterns may vary — do **not** commit passwords):

   ```env
   E2E_EMAIL=you@example.com
   E2E_PASSWORD=yourpassword
   ```

   Aliases: **`LOCAL_AUTH_EMAIL`** / **`LOCAL_AUTH_PASSWORD`**.

3. Optional overrides:

   - **`E2E_API_BASE`** — default `http://127.0.0.1:8000`
   - **`LOCAL_AUTH_FRONTEND_URL`** — default `http://127.0.0.1:8080` (must match `vite.config.ts` **port**)

4. Run:

   ```bash
   npm run auth:bootstrap
   ```

5. **Stdout** is a single **URL** with hash `#__secmanus_bootstrap=...`. In **Playwright MCP**, call **`browser_navigate`** to that URL **once** in the automation session. The app (DEV only) decodes the hash, writes `localStorage`, strips the hash, and **reloads** — you land logged in on `/`.

## Security

- The bootstrap runs only when **`import.meta.env.DEV`** is true (`src/lib/devAuthHashBootstrap.ts`). **Production builds** ignore the hash.
- The URL contains a **short-lived secret** (JWT). Do not paste into public channels; treat like a password reset link.

## Alternatives

- Import cookies via **Playwright MCP** (if supported) after a normal manual login.
- Manual login once per session (two-step form on `/auth`).
