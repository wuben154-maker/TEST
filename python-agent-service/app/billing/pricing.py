"""Resolve per-model USD pricing and compute event cost."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def compute_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    usd_per_million_input: Decimal,
    usd_per_million_output: Decimal,
) -> Decimal:
    """cost = (prompt/1e6)*in_rate + (completion/1e6)*out_rate."""
    p = max(0, int(prompt_tokens))
    c = max(0, int(completion_tokens))
    return (
        (Decimal(p) / Decimal(1_000_000)) * usd_per_million_input
        + (Decimal(c) / Decimal(1_000_000)) * usd_per_million_output
    ).quantize(Decimal("0.000001"))


def extract_token_usage_from_llm_result(response: Any) -> tuple[int, int]:
    """Best-effort token counts from LangChain ``LLMResult``."""
    prompt_t = 0
    completion_t = 0

    llm_out = getattr(response, "llm_output", None) or {}
    if isinstance(llm_out, dict):
        u = (
            llm_out.get("token_usage")
            or llm_out.get("usage_metadata")
            or llm_out.get("usage")
            or {}
        )
        if isinstance(u, dict):
            prompt_t = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
            completion_t = int(
                u.get("completion_tokens") or u.get("output_tokens") or 0
            )

    if prompt_t == 0 and completion_t == 0:
        for gen_list in getattr(response, "generations", None) or []:
            for g in gen_list:
                pt_g = 0
                ct_g = 0
                info = getattr(g, "generation_info", None) or {}
                if isinstance(info, dict):
                    meta = info.get("usage_metadata") or info.get("token_usage") or {}
                    if isinstance(meta, dict):
                        pt_g = int(
                            meta.get("prompt_tokens")
                            or meta.get("input_tokens")
                            or meta.get("input_token_count")
                            or 0
                        )
                        ct_g = int(
                            meta.get("completion_tokens")
                            or meta.get("output_tokens")
                            or meta.get("output_token_count")
                            or 0
                        )
                if pt_g == 0 and ct_g == 0:
                    msg = getattr(g, "message", None)
                    if msg is not None:
                        um = getattr(msg, "usage_metadata", None)
                        if isinstance(um, dict):
                            pt_g = int(
                                um.get("input_tokens")
                                or um.get("prompt_tokens")
                                or um.get("promptTokenCount")
                                or 0
                            )
                            ct_g = int(
                                um.get("output_tokens")
                                or um.get("completion_tokens")
                                or um.get("candidatesTokenCount")
                                or um.get("outputTokenCount")
                                or 0
                            )
                prompt_t += pt_g
                completion_t += ct_g

    return prompt_t, completion_t
