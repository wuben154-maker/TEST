#!/usr/bin/env python3
"""Apply one or more SQL files to local PostgreSQL using LOCAL_DB_* from .env.

Uses psycopg3 multi-statement execution (no psql required).
Intended for Windows when psql is not on PATH.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply SQL file(s) using LOCAL_DB_* from .env",
    )
    parser.add_argument(
        "sql_files",
        nargs="+",
        type=Path,
        help="Paths to .sql files (relative to cwd or absolute)",
    )
    args = parser.parse_args()

    load_dotenv(_service_root() / ".env")
    mode = os.environ.get("DATABASE_MODE", "local").strip().lower()
    if mode != "local":
        print(
            f"DATABASE_MODE is '{mode}', not 'local'. Refusing to apply.",
            file=sys.stderr,
        )
        return 2

    host = os.environ.get("LOCAL_DB_HOST", "localhost")
    port = int(os.environ.get("LOCAL_DB_PORT", "5432"))
    dbname = os.environ.get("LOCAL_DB_NAME", "secmanus")
    user = os.environ.get("LOCAL_DB_USER", "postgres")
    password = os.environ.get("LOCAL_DB_PASSWORD", "")

    import psycopg

    conn_str = (
        f"host={host} port={port} dbname={dbname} user={user} "
        f"password={password} connect_timeout=30"
    )

    for rel in args.sql_files:
        path = rel.resolve() if rel.is_absolute() else Path(rel).resolve()
        if not path.is_file():
            print(f"Not a file: {path}", file=sys.stderr)
            return 2
        sql_text = path.read_text(encoding="utf-8")
        print(f"Applying {path.name} -> {host}:{port}/{dbname} ...")
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)
        print(f"  OK: {path.name}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
