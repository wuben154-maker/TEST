# Development database reset (schema changes)

When migrations add columns (for example `messages.timeline` for analysis SSE replay), local PostgreSQL may be out of date.

## Option A: Run migrations

From the repo root, apply Supabase migrations to your local instance (e.g. `supabase db push` or your usual migration workflow).

## Option B: Clear all workspace app history (recommended script)

Reusable script under **`python-agent-service/scripts/db/`** (truncates messages, projects, progress, shared reports, session params, agent store; **does not** remove `auth.users` / `profiles`):

- Doc / SQL reference: `python-agent-service/scripts/db/clear_dev_app_history.sql`
- PowerShell: `python-agent-service/scripts/db/run_clear_dev_app_history.ps1`
- Python: `python-agent-service/scripts/db/run_clear_dev_app_history.py` (reads `DATABASE_URL` or **`python-agent-service/.env`** `LOCAL_DB_*`, else local Supabase default port `54322`)

```powershell
.\python-agent-service\scripts\db\run_clear_dev_app_history.ps1
```

Details: `python-agent-service/scripts/db/README.md`.

**Warning:** This wipes **all** projects and messages for that database. Use only on disposable dev databases.

### Option B2: Truncate messages only (legacy snippet)

```sql
TRUNCATE TABLE public.messages CASCADE;
TRUNCATE TABLE public.project_analysis_progress CASCADE;
```

Related OpenSpec change: `unify-agent-sse-timeline`.
