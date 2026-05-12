"""Display-layer Credits multiplier (engineering unit stays USD for gate + aggregates)."""

from __future__ import annotations

from decimal import Decimal

# Product rule: UI shows Credits where 100 Credits == USD 1.00 — gate/pricing unchanged in USD.
CREDITS_PER_USD = Decimal("100")


def credits_per_usd_int() -> int:
    """JSON-friendly scalar for APIs."""
    return int(CREDITS_PER_USD)


def usd_to_display_credits_str(usd: Decimal) -> str:
    """Credits string for summaries and tables (quantize to cents of a credit)."""
    return str((usd * CREDITS_PER_USD).quantize(Decimal("0.01")))
