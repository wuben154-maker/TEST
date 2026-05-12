#!/usr/bin/env python3
"""Test which models return reasoning process (thinking) vs reasoning result (text).

Reasoning process = step-by-step thinking (internal reasoning)
Reasoning result = final answer/conclusion (user-facing output)

These two are normally different: thinking shows "how", text shows "what".

Run from python-agent-service dir:
  python scripts/test_reasoning_models.py
  python scripts/test_reasoning_models.py --limit 5   # quick test first 5 models

Requires at least one API key in .env (GOOGLE_API_KEY, ANTHROPIC_API_KEY, etc.).

Models that typically support reasoning process (thinking):
  - Anthropic Claude (enable_anthropic_thinking=True)
  - Google Gemini 2.5/3 (enable_gemini_thinking=True)
  - OpenAI o1/o3 (reasoning models)
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REASONING_PROMPT = """Solve 17 * 23. First show your step-by-step reasoning process \
(how you calculate), then give the final answer only at the end.

Format:
1. Reasoning process: [your thinking steps]
2. Final answer: [just the number]"""


def _extract_thinking_and_text(msg) -> tuple[str, str]:
    """Extract thinking and text from AIMessage (matches deepagents_stream_adapter)."""
    from app.parsers.message_content import additional_kwargs_reasoning_text

    thinking_parts: list[str] = []
    text_parts: list[str] = []

    additional = getattr(msg, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        rk = additional_kwargs_reasoning_text(additional)
        if rk:
            thinking_parts.append(rk)

    content = getattr(msg, "content", None)
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "thinking":
                thinking_parts.append(str(block.get("thinking", "")))
            elif block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("thought") is True:
                thinking_parts.append(str(block.get("text", "")))
            elif "text" in block:
                text_parts.append(str(block.get("text", "")))
            elif isinstance(block.get("content"), str):
                text_parts.append(str(block.get("content", "")))

    if not thinking_parts and not text_parts and isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                for key in ("text", "content", "summary"):
                    v = block.get(key)
                    if isinstance(v, str) and v.strip():
                        text_parts.append(v)
                        break

    return ("".join(thinking_parts), "".join(text_parts))


async def test_model(model_id: str) -> dict:
    """Test one model, return reasoning_process, reasoning_result, and whether they differ."""
    from app.llm_gateway.factory import get_model
    from langchain_core.messages import HumanMessage

    try:
        model = get_model(model_id)
        resp = await model.ainvoke([HumanMessage(content=REASONING_PROMPT)])
        thinking, text = _extract_thinking_and_text(resp)
        thinking = (thinking or "").strip()
        text = (text or "").strip()

        has_process = bool(thinking)
        has_result = bool(text)
        are_different = has_process and has_result and thinking != text
        if has_process and has_result and not are_different:
            are_different = thinking not in text and text not in thinking

        return {
            "model_id": model_id,
            "ok": True,
            "has_reasoning_process": has_process,
            "has_reasoning_result": has_result,
            "are_different": are_different,
            "process_len": len(thinking),
            "result_len": len(text),
            "process_preview": thinking[:150] + "..." if len(thinking) > 150 else thinking,
            "result_preview": text[:150] + "..." if len(text) > 150 else text,
            "error": None,
        }
    except Exception as e:
        return {
            "model_id": model_id,
            "ok": False,
            "has_reasoning_process": False,
            "has_reasoning_result": False,
            "are_different": False,
            "process_len": 0,
            "result_len": 0,
            "process_preview": "",
            "result_preview": "",
            "error": str(e),
        }


async def main():
    parser = argparse.ArgumentParser(description="Test which models have reasoning process vs result")
    parser.add_argument("--limit", type=int, default=0, help="Limit to first N models (0=all)")
    args = parser.parse_args()

    from app.llm_gateway.registry import get_registry

    get_registry.cache_clear()
    reg = get_registry()
    models = reg.list_models()
    if args.limit > 0:
        models = models[: args.limit]
        print(f"(Limited to first {args.limit} models)\n")

    if not models:
        print("No models. Add API keys to .env (GOOGLE_API_KEY, ANTHROPIC_API_KEY, etc.)")
        return

    print("=" * 80)
    print("Reasoning Model Test")
    print("  - Reasoning process = internal thinking steps (how)")
    print("  - Reasoning result  = final answer (what)")
    print("  - Normally these should be DIFFERENT")
    print("=" * 80)
    prompt_preview = REASONING_PROMPT[:60] + "..." if len(REASONING_PROMPT) > 60 else ""
    print(f"\nTesting {len(models)} models with prompt: '{prompt_preview}'")
    print()

    results: list[dict] = []
    for i, m in enumerate(models):
        print(f"  [{i+1}/{len(models)}] {m.id}...", end=" ", flush=True)
        r = await test_model(m.id)
        results.append(r)
        if r["ok"]:
            status = []
            status.append("process[Y]" if r["has_reasoning_process"] else "process[N]")
            status.append("result[Y]" if r["has_reasoning_result"] else "result[N]")
            status.append("diff[Y]" if r["are_different"] else "diff[N]")
            print(" ".join(status))
        else:
            print(f"ERROR: {r['error'][:60]}")

    # Summary table
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Model ID':<40} {'Process':<10} {'Result':<10} {'Different':<10} {'Status'}")
    print("-" * 80)

    for r in results:
        proc = "Y" if r["has_reasoning_process"] else "N"
        res = "Y" if r["has_reasoning_result"] else "N"
        diff = "Y" if r["are_different"] else "N"
        status = "OK" if r["ok"] else f"ERR: {r['error'][:30]}"
        print(f"{r['model_id']:<40} {proc:<10} {res:<10} {diff:<10} {status}")

    ideal = [
        r for r in results
        if r["ok"] and r["has_reasoning_process"]
        and r["has_reasoning_result"] and r["are_different"]
    ]
    print("\n" + "-" * 80)
    print("Models with BOTH reasoning process AND result (and they differ):", len(ideal))
    for r in ideal:
        print(f"  - {r['model_id']} (process={r['process_len']}, result={r['result_len']} chars)")

    no_process = [
        r for r in results
        if r["ok"] and not r["has_reasoning_process"] and r["has_reasoning_result"]
    ]
    print("\nModels with result only (no reasoning process):", len(no_process))
    for r in no_process[:5]:
        print(f"  - {r['model_id']}")
    if len(no_process) > 5:
        print(f"  ... and {len(no_process) - 5} more")

    # Verbose: show sample for first ideal model
    if ideal:
        r = ideal[0]
        print("\n" + "=" * 80)
        print(f"SAMPLE (first ideal model: {r['model_id']})")
        print("=" * 80)
        print("\n[Reasoning process (thinking)]:")
        print(r["process_preview"])
        print("\n[Reasoning result (final answer)]:")
        print(r["result_preview"])


if __name__ == "__main__":
    asyncio.run(main())
