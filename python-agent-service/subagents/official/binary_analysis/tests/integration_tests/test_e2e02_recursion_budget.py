"""Integration tests for FR-30 embedded-PE recursion budget scenarios.

Covers:
- Depth-2 recursion limit: third ``recurse_child_sample`` call is blocked
  and writes a ``recursion_depth_exceeded`` Indicator (FR-30 AC-4).
- Budget exhaustion: cumulative 75k (parent) + 50k (child) > 120k hard cap
  triggers the "保子砍父" ``budget_starved`` short-circuit (FR-30 AC-5 /
  NFR-05).

All scenarios use ``FakeListChatModel`` to mock the LLM layer so no real
model credentials are required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from budget_guards import (
    BudgetCoordinator,
    RecursionDepthGuard,
    RoundBudgetGuard,
    TokenBudgetGuard,
)
from embedded_recursion import recurse_child_sample
from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Indicator, Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_model() -> FakeListChatModel:
    return FakeListChatModel(responses=["done"])


class _DummySandboxClient:
    """Minimal SandboxClient stand-in; no methods called during unit recursion."""


def _make_parent_store(analysis_id: str = "parent-integ") -> EvidenceChainStore:
    """Return an EvidenceChainStore with the minimum file_meta Indicator."""
    from schema.indicator import Confidence

    store = EvidenceChainStore(analysis_id=analysis_id)
    ind = Indicator(
        source_fr="FR-01",
        indicator_type="file_meta",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        kind="fact",
        data={
            "absolute_path": f"/workspace/{analysis_id}/sample.docx",
            "size_bytes": 4096,
            "format": "OOXML_DOCX_MACRO",
            "fingerprints": {"sha256": "a" * 64, "md5": "b" * 32, "sha1": "c" * 40},
        },
    )
    store.append(Bucket.file_meta, ind)
    return store


def _make_coordinator(
    *,
    token_budget: int = 80_000,
    max_depth: int = 2,
    child_floor: int = 50_000,
) -> BudgetCoordinator:
    return BudgetCoordinator(
        token_guard=TokenBudgetGuard(budget=token_budget),
        round_guard=RoundBudgetGuard(max_rounds=15),
        depth_guard=RecursionDepthGuard(max_depth=max_depth),
        child_floor=child_floor,
    )


# ---------------------------------------------------------------------------
# Scenario 1: Depth-2 limit — third recursive call is rejected
# ---------------------------------------------------------------------------


class TestRecursionDepthLimit:
    """FR-30 AC-4: depth guard blocks recursion at max_depth=2."""

    pytestmark = pytest.mark.asyncio

    async def test_depth_2_completes_but_depth_3_is_rejected(
        self, tmp_path: Path
    ) -> None:
        """Two successful recursions; third call at depth>2 writes recursion_depth_exceeded.

        The RecursionDepthGuard counter is pre-loaded to simulate that 2 levels of
        nested recursion are already active (i.e. we are inside a depth-2 call stack).
        A further enter() pushes depth to 3 > max_depth=2 and must be blocked.
        """
        parent_store = _make_parent_store("p-depth-integ")
        coord = _make_coordinator(max_depth=2)
        depth_guard = coord.depth_guard

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": []}

        with patch("embedded_recursion.build_binary_analyst_agent", return_value=mock_graph):
            # Depth-1 recursion — allowed
            r1 = await recurse_child_sample(
                parent_store,
                "child-d1",
                "/workspace/p-depth-integ/children/child-d1.bin",
                coord,
                depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="p-depth-integ",
                child_sha256="aa" * 32,
                child_suggested_format="PE32",
            )
            assert r1["status"] == "completed", r1

        # Simulate a nested call stack: pre-enter the guard twice to represent
        # being inside 2 levels of active recursion.  The next enter() inside
        # recurse_child_sample will push depth to 3 > max_depth=2.
        depth_guard.enter()  # depth = 1 (representing outer frame)
        depth_guard.enter()  # depth = 2 (representing inner frame)

        # Third attempt: exceeds max_depth=2 → must be rejected without invoking graph
        r3 = await recurse_child_sample(
            parent_store,
            "child-d3",
            "/workspace/p-depth-integ/children/child-d3.bin",
            coord,
            depth_guard,
            model=_fake_model(),
            sandbox_client=_DummySandboxClient(),
            skills_root=tmp_path,
            parent_analysis_id="p-depth-integ",
        )
        assert r3["status"] == "recursion_depth_exceeded"
        assert "error" in r3

        # embedded_payloads bucket must contain recursion_depth_exceeded Indicator
        snapshot = parent_store.snapshot()
        exceeded = [
            ind
            for ind in snapshot.embedded_payloads
            if ind.indicator_type == "recursion_depth_exceeded"
        ]
        assert len(exceeded) >= 1
        assert exceeded[0].data["child_sample_id"] == "child-d3"

    async def test_delivery_chain_doc_has_two_links_for_successful_recursions(
        self, tmp_path: Path
    ) -> None:
        """After 2 successful recursions, delivery_chain_doc has 2 parent_child_links."""
        parent_store = _make_parent_store("p-two-links")
        coord = _make_coordinator(max_depth=2)

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": []}

        with patch("embedded_recursion.build_binary_analyst_agent", return_value=mock_graph):
            await recurse_child_sample(
                parent_store,
                "child-link-1",
                "/workspace/p-two-links/children/child-link-1.bin",
                coord,
                coord.depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="p-two-links",
                child_sha256="cc" * 32,
                child_suggested_format="PE32",
            )
            await recurse_child_sample(
                parent_store,
                "child-link-2",
                "/workspace/p-two-links/children/child-link-2.bin",
                coord,
                coord.depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="p-two-links",
                child_sha256="dd" * 32,
                child_suggested_format="DLL",
            )

        snapshot = parent_store.snapshot()
        links = [
            ind
            for ind in snapshot.delivery_chain_doc
            if ind.indicator_type == "parent_child_link"
        ]
        assert len(links) == 2
        child_ids = {lnk.data["child_sample_id"] for lnk in links}
        assert child_ids == {"child-link-1", "child-link-2"}


# ---------------------------------------------------------------------------
# Scenario 2: Budget exhaustion — "保子砍父" short-circuits parent
# ---------------------------------------------------------------------------


class TestBudgetExhaustion:
    """FR-30 AC-5 / NFR-05: token budget exhaustion triggers 保子砍父 short-circuit."""

    pytestmark = pytest.mark.asyncio

    async def test_parent_budget_starved_when_remaining_below_child_floor(
        self, tmp_path: Path
    ) -> None:
        """Parent has only 10k remaining (< 50k child_floor) → status=budget_starved."""
        parent_store = _make_parent_store("p-budget-integ")
        coord = _make_coordinator(
            token_budget=80_000,
            child_floor=50_000,
        )
        # Simulate parent consuming 75k of 80k; 5k remaining < 50k child_floor
        coord.token_guard.record(75_000)
        # Enter depth=1 so prioritize_children applies the child_floor policy
        coord.depth_guard.enter()

        result = await recurse_child_sample(
            parent_store,
            "child-budget-starved",
            "/workspace/p-budget-integ/children/child-budget-starved.bin",
            coord,
            coord.depth_guard,
            model=_fake_model(),
            sandbox_client=_DummySandboxClient(),
            skills_root=tmp_path,
            parent_analysis_id="p-budget-integ",
            child_sha256="ee" * 32,
            child_suggested_format="PE32",
        )

        assert result["status"] == "budget_starved"
        assert result["child_verdict"] == "unknown_budget_starved"
        # delivery_chain_doc still gets a parent_child_link for traceability
        snapshot = parent_store.snapshot()
        links = [
            ind
            for ind in snapshot.delivery_chain_doc
            if ind.indicator_type == "parent_child_link"
        ]
        assert len(links) == 1
        assert links[0].data["child_verdict"] == "unknown_budget_starved"

    async def test_budget_exhaustion_produces_unknown_downgrade(
        self, tmp_path: Path
    ) -> None:
        """Parent 75k + child_floor 50k > 120k hard cap path: budget_starved returned."""
        parent_store = _make_parent_store("p-hardcap")
        # Use token budget = 120_000 (hard cap), consume 75k
        coord = BudgetCoordinator(
            token_guard=TokenBudgetGuard(budget=120_000, hard_cap=120_000),
            round_guard=RoundBudgetGuard(max_rounds=15),
            depth_guard=RecursionDepthGuard(max_depth=2),
            child_floor=50_000,
        )
        coord.token_guard.record(75_000)  # 45k remaining < 50k child_floor
        coord.depth_guard.enter()  # depth = 1 to trigger child_floor policy

        result = await recurse_child_sample(
            parent_store,
            "child-hardcap",
            "/workspace/p-hardcap/children/child-hardcap.bin",
            coord,
            coord.depth_guard,
            model=_fake_model(),
            sandbox_client=_DummySandboxClient(),
            skills_root=tmp_path,
            parent_analysis_id="p-hardcap",
        )

        assert result["status"] == "budget_starved"
        # Confirm delivery_chain_doc link is written with unknown_budget_starved verdict
        snapshot = parent_store.snapshot()
        links = [
            i
            for i in snapshot.delivery_chain_doc
            if i.indicator_type == "parent_child_link"
        ]
        assert len(links) == 1
        assert "budget_starved" in links[0].data["child_verdict"]
