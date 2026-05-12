#!/usr/bin/env python3
"""Run upload->analyze E2E snapshot test and print the LLM-first-input report to stdout.

Usage (from python-agent-service directory):

  python scripts/e2e_upload_llm_first_input_report.py

Equivalent:

  python -m pytest tests/test_e2e_upload_to_llm_first_message.py -v -s --tb=short
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(ROOT / "tests" / "test_e2e_upload_to_llm_first_message.py"),
        "-v",
        "-s",
        "--tb=short",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
