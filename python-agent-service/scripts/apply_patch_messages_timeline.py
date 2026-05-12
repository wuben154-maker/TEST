"""Apply patch_messages_timeline.sql using LOCAL_DB_* or DATABASE_URL (same rules as scripts/db/run_clear_dev_app_history.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SERVICE_ROOT.parent
_AGENT_ENV = _SERVICE_ROOT / ".env"


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _url() -> str:
    u = os.environ.get("DATABASE_URL", "").strip()
    if u:
        return u
    merged: dict[str, str] = {}
    for p in (_REPO_ROOT / ".env", _AGENT_ENV):
        merged.update(_parse_dotenv(p))
    u = merged.get("DATABASE_URL", "").strip()
    if u:
        return u
    h = merged.get("LOCAL_DB_HOST", "").strip()
    port = merged.get("LOCAL_DB_PORT", "").strip()
    name = merged.get("LOCAL_DB_NAME", "").strip()
    user = merged.get("LOCAL_DB_USER", "").strip()
    password = merged.get("LOCAL_DB_PASSWORD", "")
    if not (h and port and name and user):
        raise SystemExit("Set DATABASE_URL or LOCAL_DB_* in python-agent-service/.env")
    pw = quote_plus(password) if password else ""
    auth = f"{quote_plus(user)}:{pw}" if pw else quote_plus(user)
    return f"postgresql://{auth}@{h}:{port}/{name}"


def main() -> int:
    sql_path = Path(__file__).resolve().parent / "db" / "patch_messages_timeline.sql"
    sql = sql_path.read_text(encoding="utf-8")
    try:
        import psycopg2
    except ImportError:
        print("Install psycopg2-binary", file=sys.stderr)
        return 1
    conn = psycopg2.connect(_url())
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()
    print("OK:", sql_path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
