#!/usr/bin/env python3
"""Print full Reasoning (thinking) and reply text for every OpenCode Zen model.

Uses the same extraction rules as app.parsers.deepagents_stream_adapter._extract_thinking_and_text
(Anthropic thinking blocks, OpenAI reasoning_content, Gemini thought parts, plain string content).

Run from python-agent-service directory:

  python scripts/print_zen_llm_reasoning.py
  python scripts/print_zen_llm_reasoning.py --model opencode/gpt-5.4
  python scripts/print_zen_llm_reasoning.py --prompt "Say hello in 5 words."

Requires OPENCODE_ZEN_API_KEY in environment or .env.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

DEFAULT_PROMPT = (
    "Solve 7 * 8 briefly: if you have internal reasoning, use it; "
    "then give the final numeric answer on the last line."
)


def _configure_stdout_utf8() -> None:
    """Avoid UnicodeEncodeError on Windows consoles when printing model output (e.g. U+202F)."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _zen_api_key_ready() -> bool:
    from dotenv import load_dotenv

    load_dotenv(SERVICE_ROOT / ".env")
    k = (os.getenv("OPENCODE_ZEN_API_KEY") or "").strip()
    if not k:
        return False
    if k.startswith("your-") or k == "sk-xxx":
        return False
    return True


async def main_async(*, model_id: str | None, user_prompt: str) -> None:
    from langchain_core.messages import HumanMessage

    from app.llm_gateway.factory import get_model
    from app.llm_gateway.registry import get_registry
    from app.parsers.deepagents_stream_adapter import _extract_thinking_and_text

    get_registry.cache_clear()
    reg = get_registry()
    models = [m for m in reg.list_models() if m.provider == "opencode"]
    if model_id:
        models = [m for m in models if m.id == model_id]
        if not models:
            print(f"No Zen model matched id={model_id!r}. Available opencode ids:")
            for m in reg.list_models():
                if m.provider == "opencode":
                    print(f"  {m.id}")
            return

    if not models:
        print("No OpenCode Zen models in registry (check OPENCODE_ZEN_API_KEY and config/llm_gateway.yaml).")
        return

    print("=" * 88)
    print("OpenCode Zen — LLM Reasoning + reply dump")
    print(f"Prompt: {user_prompt!r}")
    print(f"Models: {len(models)}")
    print("=" * 88)

    for idx, info in enumerate(models, start=1):
        sep = "=" * 88
        print(f"\n{sep}\n[{idx}/{len(models)}] {info.id} (sdk={info.sdk_model})\n{sep}")

        try:
            model = get_model(info.id)
            resp = await model.ainvoke([HumanMessage(content=user_prompt)])
            reasoning, reply = _extract_thinking_and_text(resp)

            print("\n--- Reasoning (extracted thinking / reasoning_content / thought parts) ---")
            if (reasoning or "").strip():
                print(reasoning)
            else:
                print("(empty)")

            print("\n--- Reply (extracted user-facing text) ---")
            if (reply or "").strip():
                print(reply)
            else:
                print("(empty)")

            # When extraction misses provider-specific shapes, show raw message fields for debugging.
            if not str(reasoning).strip() and not str(reply).strip():
                content = getattr(resp, "content", None)
                add_kw = getattr(resp, "additional_kwargs", None)
                meta = getattr(resp, "response_metadata", None)
                print("\n--- Debug: raw AIMessage slices (extraction returned empty) ---")
                print(f"content type={type(content).__name__!r} repr={repr(content)[:2000]}")
                print(f"additional_kwargs keys={list(add_kw.keys()) if isinstance(add_kw, dict) else add_kw!r}")
                if isinstance(add_kw, dict) and add_kw:
                    print(f"additional_kwargs={repr(add_kw)[:2000]}")
                print(f"response_metadata={repr(meta)[:2000] if meta else meta!r}")
        except Exception as e:
            print(f"\n--- ERROR ---\n{e!r}")


def main() -> None:
    _configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Print Zen LLM reasoning + reply for all opencode models")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Single model id (e.g. opencode/gpt-5.4). Default: all Zen models.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=DEFAULT_PROMPT,
        help="User message sent to each model.",
    )
    args = parser.parse_args()

    if not _zen_api_key_ready():
        print(
            "Missing or placeholder OPENCODE_ZEN_API_KEY. "
            "Set it in .env or the environment, then re-run."
        )
        sys.exit(1)

    asyncio.run(main_async(model_id=args.model, user_prompt=args.prompt))


if __name__ == "__main__":
    main()
