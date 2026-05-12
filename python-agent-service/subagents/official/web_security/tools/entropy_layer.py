"""L1b high Shannon entropy windows over UTF-8 bytes (weak signal)."""

from __future__ import annotations

import math
import string
from collections import Counter

from .models import Evidence, Finding, Signal


def _shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    ent = 0.0
    for c in counts.values():
        p = c / n
        ent -= p * math.log2(p)
    return ent


def entropy_findings(
    text: str,
    *,
    window: int = 64,
    step: int = 32,
    threshold: float = 7.4,
) -> list[Finding]:
    """
    Flag a single aggregate finding when any window exceeds entropy threshold.
    Uses printable-heavy windows to reduce noise on raw binary-ish blobs in text.
    """
    raw = text.encode("utf-8", errors="replace")
    if len(raw) < window:
        return []

    max_e = 0.0
    max_off = 0
    for i in range(0, len(raw) - window + 1, step):
        chunk = raw[i : i + window]
        e = _shannon_entropy(chunk)
        if e > max_e:
            max_e = e
            max_off = i

    if max_e < threshold:
        return []

    snippet = raw[max_off : max_off + window].decode("utf-8", errors="replace")
    printable_ratio = sum(1 for c in snippet if c in string.printable) / max(len(snippet), 1)
    if printable_ratio < 0.6:
        return []

    return [
        Finding(
            id=f"entropy-window-{max_off}",
            category="other",
            severity="low",
            confidence=0.45,
            layer="L1",
            evidence=Evidence(
                snippet=snippet[:220],
                start=max_off,
                end=max_off + window,
                location=f"L1:entropy:window:{max_e:.2f}",
            ),
            signals=[Signal(type="pattern", name="high_entropy_window", weight=0.35)],
        )
    ]
