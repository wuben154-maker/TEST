"""Execute clear_dev_app_history (TRUNCATE app tables) using psycopg2 (no psql).

Usage (from repo root):
  python python-agent-service/scripts/db/run_clear_dev_app_history.py

From python-agent-service directory:
  python scripts/db/run_clear_dev_app_history.py

Connection resolution order:
  1. Environment variable DATABASE_URL
  2. DATABASE_URL in repo-root .env or python-agent-service/.env
  3. LOCAL_DB_* in those .env files (DATABASE_MODE=local style)
  4. Fallback: local Supabase default (127.0.0.1:54322)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SERVICE_ROOT.parent
_AGENT_ENV = _SERVICE_ROOT / ".env"
_DEFAULT_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# Tables to clear (order not significant; CASCADE handles FKs). Skip if not installed.
_TABLES_TO_CLEAR = (
    "project_analysis_progress",
    "messages",
    "projects",
    "shared_reports",
    "session_parameters",
    "parameter_callbacks",
    "agent_store",
)


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        out[key] = val
    return out


def _url_from_local_db(vals: dict[str, str]) -> str | None:
    host = vals.get("LOCAL_DB_HOST", "").strip()
    port = vals.get("LOCAL_DB_PORT", "").strip()
    name = vals.get("LOCAL_DB_NAME", "").strip()
    user = vals.get("LOCAL_DB_USER", "").strip()
    password = vals.get("LOCAL_DB_PASSWORD", "")
    if not (host and port and name and user):
        return None
    pw = quote_plus(password) if password else ""
    auth = f"{quote_plus(user)}:{pw}" if pw else quote_plus(user)
    return f"postgresql://{auth}@{host}:{port}/{name}"


def _load_database_url() -> tuple[str, str]:
    """Returns (url, source_description for logging)."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url, "environment DATABASE_URL"

    merged: dict[str, str] = {}
    for p in (_REPO_ROOT / ".env", _AGENT_ENV):
        merged.update(_parse_dotenv(p))

    url = merged.get("DATABASE_URL", "").strip()
    if url:
        return url, "DATABASE_URL from .env"

    built = _url_from_local_db(merged)
    if built:
        return built, "LOCAL_DB_* from python-agent-service/.env"

    return _DEFAULT_URL, "default Supabase local (127.0.0.1:54322)"


def _existing_public_tables(cur, names: tuple[str, ...]) -> list[str]:
    cur.execute(
        """
        SELECT tablename FROM pg_catalog.pg_tables
        WHERE schemaname = 'public' AND tablename = ANY(%s)
        """,
        (list(names),),
    )
    found = {row[0] for row in cur.fetchall()}
    return [t for t in names if t in found]


def main() -> int:
    url, source = _load_database_url()
    print(f"Connecting via: {source}")
    if url == _DEFAULT_URL:
        print("(Set DATABASE_URL or configure python-agent-service/.env LOCAL_DB_* to avoid this fallback.)")

    try:
        import psycopg2
        from psycopg2 import sql as psql
    except ImportError:
        print(
            "psycopg2 is required. Install: pip install psycopg2-binary\n"
            "Run from this repo with venv: python-agent-service\\.venv\\Scripts\\python scripts\\db\\run_clear_dev_app_history.py",
            file=sys.stderr,
        )
        return 1

    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            existing = _existing_public_tables(cur, _TABLES_TO_CLEAR)
            missing = [t for t in _TABLES_TO_CLEAR if t not in existing]
            if missing:
                print("Skipping tables not present in DB:", ", ".join(missing))
            if not existing:
                print("No matching tables to truncate.", file=sys.stderr)
                return 1
            stmt = psql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                psql.SQL(", ").join(psql.Identifier("public", t) for t in existing)
            )
            cur.execute(stmt)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("clear_dev_app_history completed OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
