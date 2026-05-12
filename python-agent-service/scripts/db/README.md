# Database utility scripts (`python-agent-service/scripts/db`)

## `clear_dev_app_history` (Python)

Deletes **application history** only:

- `projects`, `messages`, `project_analysis_progress`
- `shared_reports`
- `session_parameters`, `parameter_callbacks`
- `agent_store` (skipped if table does not exist)

It does **not** remove `auth.users`, `public.profiles`, or migration history.

### Prerequisites

- `psycopg2-binary` (same as backend).
- Connection: `DATABASE_URL`, or **`python-agent-service/.env`** `LOCAL_DB_*` / `DATABASE_URL`, or repo-root `.env`.

### Run

**From repo root:**

```powershell
python python-agent-service\scripts\db\run_clear_dev_app_history.py
```

**From `python-agent-service` (with venv activated):**

```powershell
python scripts\db\run_clear_dev_app_history.py
```

**PowerShell wrapper (resolves `.venv\Scripts\python.exe` under this package):**

```powershell
.\python-agent-service\scripts\db\run_clear_dev_app_history.ps1
```

**With explicit URL:**

```powershell
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@127.0.0.1:54322/postgres"
python python-agent-service\scripts\db\run_clear_dev_app_history.py
```

### Files

- `clear_dev_app_history.sql` — human-readable list of intended tables (execution is via Python so missing tables are skipped).

### Troubleshooting

- **Connection refused** — start Postgres / `supabase start`, or set `DATABASE_URL`.
- **psycopg2 missing** — `pip install psycopg2-binary` in `python-agent-service` venv.

See also repo `docs/DEV_DB_RESET.md`.
