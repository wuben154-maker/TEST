"""Token, round, and recursion budget guards (FR-08 / NFR-05 / NFR-07 / ADR-DOC-03)."""

from __future__ import annotations

from errors import BudgetExceeded
from prompts.system_prompt import (
    CONVERGENCE_THRESHOLD_RATIO,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_TOKEN_BUDGET,
    TOKEN_BUDGET_HARD_CAP,
)

__all__ = [
    "BudgetCoordinator",
    "RecursionDepthGuard",
    "RoundBudgetGuard",
    "TokenBudgetGuard",
]


class TokenBudgetGuard:
    """Track cumulative LLM token consumption for FR-08 AC-9 / NFR-05.

    The guard is passive: callers ``record`` each round's prompt +
    completion tokens (from ``UsageMetadata``) and consult
    :attr:`should_converge` / :attr:`exceeded` to steer the orchestrator.
    Breaching the hard budget raises :class:`BudgetExceeded` so the
    calling layer can short-circuit to the facts-only report.

    For recursive document scenarios (FR-08 AC-6 / ADR-DOC-03), callers
    may invoke :meth:`try_extend_to_hard_cap` to request a one-time
    budget extension up to ``hard_cap`` (default
    :data:`TOKEN_BUDGET_HARD_CAP` = 120 000) before the hard-limit raise.

    Args:
        budget: Aggregate token ceiling for the session (binary-mode
            default ``50_000``; document-mode callers should pass
            :data:`~prompts.system_prompt.DOC_DEFAULT_TOKEN_BUDGET`
            = 80 000).
        threshold_ratio: Fraction of ``budget`` at which the guard flips
            :attr:`should_converge` to ``True`` so the Agent enters
            comprehensive judgment.  Must be in ``(0, 1]``.
        hard_cap: Absolute token ceiling beyond which no extension is
            permitted.  Used by :meth:`try_extend_to_hard_cap` for the
            recursive "保子砍父" escape hatch (FR-08 AC-6).
    """

    def __init__(
        self,
        *,
        budget: int = DEFAULT_TOKEN_BUDGET,
        threshold_ratio: float = CONVERGENCE_THRESHOLD_RATIO,
        hard_cap: int = TOKEN_BUDGET_HARD_CAP,
    ) -> None:
        if budget <= 0:
            msg = "budget must be positive"
            raise ValueError(msg)
        if not 0 < threshold_ratio <= 1:
            msg = "threshold_ratio must be in (0, 1]"
            raise ValueError(msg)
        if hard_cap < budget:
            msg = "hard_cap must be >= budget"
            raise ValueError(msg)
        self._budget = budget
        self._threshold_ratio = threshold_ratio
        self._threshold = int(budget * threshold_ratio)
        self._hard_cap = hard_cap
        self._consumed = 0

    @property
    def budget(self) -> int:
        """Aggregate token ceiling configured for this guard."""
        return self._budget

    @property
    def hard_cap(self) -> int:
        """Absolute token ceiling; :meth:`try_extend_to_hard_cap` cannot exceed this."""
        return self._hard_cap

    @property
    def consumed(self) -> int:
        """Total tokens recorded so far."""
        return self._consumed

    @property
    def remaining(self) -> int:
        """Tokens remaining until the hard budget is reached (never negative)."""
        return max(0, self._budget - self._consumed)

    @property
    def should_converge(self) -> bool:
        """True once :attr:`consumed` is at or above the convergence threshold."""
        return self._consumed >= self._threshold

    @property
    def exceeded(self) -> bool:
        """True once the hard budget has been fully consumed."""
        return self._consumed >= self._budget

    def record(self, tokens: int) -> None:
        """Add one round's token usage to the running total.

        Args:
            tokens: Non-negative count of tokens consumed in the round.
        """
        if tokens < 0:
            msg = "tokens must be non-negative"
            raise ValueError(msg)
        self._consumed += tokens

    def enforce(self) -> None:
        """Raise :class:`BudgetExceeded` when the hard budget is breached."""
        if self.exceeded:
            msg = (
                f"LLM token budget exceeded: consumed={self._consumed} "
                f"budget={self._budget}"
            )
            raise BudgetExceeded(
                msg,
                details={"consumed": self._consumed, "budget": self._budget},
                reason="token",
            )

    def try_extend_to_hard_cap(self) -> bool:
        """Attempt a one-time budget extension to :attr:`hard_cap` (FR-08 AC-6).

        Called when a recursive document scenario has exhausted the
        default budget but a child sample has not yet completed analysis.
        Extends :attr:`budget` to :attr:`hard_cap` and recomputes the
        convergence threshold.

        Returns:
            ``True`` if the extension succeeded (budget < hard_cap before
            the call); ``False`` if the budget was already at or beyond
            the hard cap and no change was made.
        """
        if self._budget >= self._hard_cap:
            return False
        self._budget = self._hard_cap
        self._threshold = int(self._budget * self._threshold_ratio)
        return True


class RoundBudgetGuard:
    """Enforce the NFR-07 maximum-LLM-rounds constraint.

    Args:
        max_rounds: Maximum number of LLM rounds allowed per session
            (binary-mode default ``10``; document-mode callers should
            pass
            :data:`~prompts.system_prompt.DOC_DEFAULT_MAX_ROUNDS`
            = 15).
    """

    def __init__(self, *, max_rounds: int = DEFAULT_MAX_ROUNDS) -> None:
        if max_rounds <= 0:
            msg = "max_rounds must be positive"
            raise ValueError(msg)
        self._max = max_rounds
        self._rounds = 0

    @property
    def max_rounds(self) -> int:
        """Configured maximum number of LLM rounds."""
        return self._max

    @property
    def rounds(self) -> int:
        """Number of rounds recorded so far."""
        return self._rounds

    @property
    def remaining(self) -> int:
        """Rounds remaining before :meth:`tick` raises (never negative)."""
        return max(0, self._max - self._rounds)

    def tick(self) -> None:
        """Record one LLM round; raise :class:`BudgetExceeded` on overflow."""
        self._rounds += 1
        if self._rounds > self._max:
            msg = f"LLM round budget exceeded: rounds={self._rounds} max={self._max}"
            raise BudgetExceeded(
                msg,
                details={"rounds": self._rounds, "max_rounds": self._max},
                reason="round",
            )


class RecursionDepthGuard:
    """Track same-graph self-recursion depth and enforce the ADR-DOC-03 limit.

    This guard is shared across e2e01 and e2e02 analysis modes (IR-DOC-03)
    to prevent depth-bypass via document → PE → overlay-document chains.
    Callers invoke :meth:`enter` at the start of each recursive sub-analysis
    and :meth:`exit` (or use as a context manager) when it completes.

    Args:
        max_depth: Maximum recursion depth permitted.  Default ``2``
            matches ADR-DOC-03 方案 C (Office → PE; one level of nesting).
    """

    def __init__(self, *, max_depth: int = 2) -> None:
        if max_depth <= 0:
            msg = "max_depth must be positive"
            raise ValueError(msg)
        self._max_depth = max_depth
        self._depth = 0

    @property
    def max_depth(self) -> int:
        """Configured maximum recursion depth."""
        return self._max_depth

    @property
    def current_depth(self) -> int:
        """Current nesting level (0 = top-level, 1 = first recursive call, …)."""
        return self._depth

    def enter(self) -> None:
        """Record entry into a recursive sub-analysis.

        Increments the depth counter.  Raises :class:`BudgetExceeded`
        with ``reason="recursion_budget"`` if the resulting depth would
        exceed :attr:`max_depth` (FR-30 AC-4 / ADR-DOC-03).

        Raises:
            BudgetExceeded: Depth limit exceeded.
        """
        self._depth += 1
        if self._depth > self._max_depth:
            msg = (
                f"Recursion depth limit exceeded: depth={self._depth} "
                f"max_depth={self._max_depth}"
            )
            raise BudgetExceeded(
                msg,
                details={"depth": self._depth, "max_depth": self._max_depth},
                reason="recursion_budget",
            )

    def exit(self) -> None:
        """Record exit from a recursive sub-analysis.

        Decrements the depth counter; never goes below zero.
        """
        self._depth = max(0, self._depth - 1)

    def __enter__(self) -> RecursionDepthGuard:
        self.enter()
        return self

    def __exit__(self, *_: object) -> None:
        self.exit()


class BudgetCoordinator:
    """Combine token / round / depth guards and implement "保子砍父" strategy.

    "保子砍父" (prioritise children over parent) is the ADR-DOC-03 budget
    allocation policy for recursive document analysis (FR-08 AC-5):

    - When recursion depth ≥ 1 and remaining tokens < ``child_floor``,
      the parent analysis is starved to zero and all remaining budget is
      reserved for the child sample.
    - When depth is 0 (top-level), the parent may use all remaining tokens.

    The coordinator also exposes :meth:`request_hard_cap_extension` to
    implement the one-time 80k → 120k extension permitted by FR-08 AC-6.

    Args:
        token_guard: Shared :class:`TokenBudgetGuard` instance.
        round_guard: Shared :class:`RoundBudgetGuard` instance.
        depth_guard: Shared :class:`RecursionDepthGuard` instance.
        child_floor: Minimum tokens to reserve for a child sub-analysis
            when depth ≥ 1.  Defaults to the e2e01 binary-mode budget
            (``DEFAULT_TOKEN_BUDGET`` = 50 000) so child PE analysis can
            run at full capacity.
    """

    def __init__(
        self,
        *,
        token_guard: TokenBudgetGuard,
        round_guard: RoundBudgetGuard,
        depth_guard: RecursionDepthGuard,
        child_floor: int = DEFAULT_TOKEN_BUDGET,
    ) -> None:
        if child_floor < 0:
            msg = "child_floor must be non-negative"
            raise ValueError(msg)
        self._token = token_guard
        self._round = round_guard
        self._depth = depth_guard
        self._child_floor = child_floor

    @property
    def token_guard(self) -> TokenBudgetGuard:
        """Shared token budget guard."""
        return self._token

    @property
    def round_guard(self) -> RoundBudgetGuard:
        """Shared round budget guard."""
        return self._round

    @property
    def depth_guard(self) -> RecursionDepthGuard:
        """Shared recursion depth guard."""
        return self._depth

    def prioritize_children(self, analysis_id: str) -> int:  # noqa: ARG002
        """Compute parent token allocation under the "保子砍父" policy (FR-08 AC-5).

        When recursion depth ≥ 1 and the remaining budget is less than
        ``child_floor``, all remaining tokens are reserved for the child
        sample (parent allocation = 0).  When the remaining budget exceeds
        ``child_floor``, the parent may use ``remaining - child_floor``
        tokens.  At depth 0, the parent retains the full remaining budget.

        Args:
            analysis_id: ULID of the parent analysis session (reserved for
                future per-analysis accounting; not used in the current
                implementation).

        Returns:
            Maximum tokens the parent analysis may consume.  May be zero
            if the child floor consumes all remaining budget.
        """
        remaining = self._token.remaining
        if self._depth.current_depth < 1:
            return remaining
        if remaining <= self._child_floor:
            return 0
        return remaining - self._child_floor

    def request_hard_cap_extension(self) -> bool:
        """Request the FR-08 AC-6 one-time hard-cap extension (80k → 120k).

        Delegates to :meth:`TokenBudgetGuard.try_extend_to_hard_cap`.
        Callers should only invoke this when in a recursive sub-analysis
        (depth ≥ 1) and the default budget is exhausted before the child
        sample has completed (ADR-DOC-03 "保子砍父" escape hatch).

        Returns:
            ``True`` if the extension succeeded; ``False`` if already at
            or beyond the hard cap.
        """
        return self._token.try_extend_to_hard_cap()
