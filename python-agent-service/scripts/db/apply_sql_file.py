#!/usr/bin/env python3
"""Apply a SQL file using LOCAL_DB_* from python-agent-service/.env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _split_statements(sql: str) -> list[str]:
    lines: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    out: list[str] = []
    for chunk in text.split(";"):
        c = chunk.strip()
        if c:
            out.append(c)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: apply_sql_file.py <path-to.sql>", file=sys.stderr)
        return 2
    sql_path = Path(sys.argv[1])
    if not sql_path.is_file():
        print(f"Not a file: {sql_path}", file=sys.stderr)
        return 2

    env_file = _service_root() / ".env"
    load_dotenv(env_file)
    host = os.environ.get("LOCAL_DB_HOST", "localhost")
    port = int(os.environ.get("LOCAL_DB_PORT", "5432"))
    dbname = os.environ.get("LOCAL_DB_NAME", "secmanus")
    user = os.environ.get("LOCAL_DB_USER", "postgres")
    password = os.environ.get("LOCAL_DB_PASSWORD", "")

    sql_text = sql_path.read_text(encoding="utf-8")
    statements = _split_statements(sql_text)
    if not statements:
        print("No statements to run.", file=sys.stderr)
        return 1

    try:
        import psycopg
    except ImportError:
        import psycopg2 as psycopg  # type: ignore

    conn = psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=20,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                cur.execute(stmt)
        print(
            f"OK: {len(statements)} statement(s) applied to "
            f"{host}:{port}/{dbname}"
        )
        print(f"    file: {sql_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
