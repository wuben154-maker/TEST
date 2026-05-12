"""Integration: print Reasoning + reply for all OpenCode Zen models (real API).

Run with a configured key and stdio visible:

  pytest tests/test_print_zen_llm_reasoning.py -s -m integration

Skipped when OPENCODE_ZEN_API_KEY is unset or placeholder.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _load_print_zen_module():
    path = SERVICE_ROOT / "scripts" / "print_zen_llm_reasoning.py"
    spec = importlib.util.spec_from_file_location("print_zen_llm_reasoning", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _zen_key_configured() -> bool:
    from dotenv import load_dotenv

    load_dotenv(SERVICE_ROOT / ".env")
    k = (os.getenv("OPENCODE_ZEN_API_KEY") or "").strip()
    if not k or k.startswith("your-") or k == "sk-xxx":
        return False
    return True


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not _zen_key_configured(), reason="OPENCODE_ZEN_API_KEY required for Zen LLM probe")
async def test_print_all_zen_models_reasoning_and_reply() -> None:
    mod = _load_print_zen_module()
    await mod.main_async(model_id=None, user_prompt=mod.DEFAULT_PROMPT)
