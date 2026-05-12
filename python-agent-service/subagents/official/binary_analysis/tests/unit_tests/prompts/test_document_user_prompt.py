"""Unit tests for render_document_user_prompt (C12, FR-08 AC-1).

Covers:
- Pure-function contract: deterministic, no side-effects.
- Template structure: all 9 named blocks appear in the rendered output.
- Untrusted-content wrapping: IOC and VBA sections enclosed in delimiter tags.
- VBA truncation integration: function indirectly exercises truncate_vba_source
  via caller convention (caller must pre-truncate; we verify the result passes
  through verbatim).
- Fixture regression: fixed inputs produce stable output.
"""

from __future__ import annotations

import pytest

from prompts.document_user_prompt import render_document_user_prompt
from prompts.sanitize import CLOSE_TAG, OPEN_TAG, truncate_vba_source

# ---------------------------------------------------------------------------
# Shared test fixture
# ---------------------------------------------------------------------------

_ANALYSIS_ID = "01HZ000000000000000000TEST"

_FIXTURE_KWARGS = dict(
    analysis_id=_ANALYSIS_ID,
    metadata='{"sha256": "aabbcc", "size_bytes": 4096, "mime_type": "application/vnd.ms-excel"}',
    document_format="ooxml_xlsm",
    document_tier="P1",
    document_analysis_compact="streams=3 macros=1 embedded_objects=0",
    macro_analysis_compact="simulation_status=ok simulation_gaps_count=0",
    embedded_payloads_compact="count=0",
    ioc_candidates_sanitized="http://evil.example/payload.exe [IP:1.2.3.4]",
    vba_source_sanitized='Sub Auto_Open()\n  Shell "cmd.exe"\nEnd Sub',
    child_verdicts_table="",
)


def _render(**overrides: str) -> str:
    kwargs = dict(_FIXTURE_KWARGS, **overrides)
    return render_document_user_prompt(**kwargs)


# ---------------------------------------------------------------------------
# Structure: all 9 template blocks present
# ---------------------------------------------------------------------------


class TestTemplateStructure:
    """render_document_user_prompt output must contain all named blocks."""

    def test_contains_metadata_block(self) -> None:
        out = _render()
        assert "[样本元数据]" in out

    def test_contains_format_tier_block(self) -> None:
        out = _render()
        assert "[格式与分层]" in out
        assert "document_format=ooxml_xlsm" in out
        assert "document_tier=P1" in out

    def test_contains_document_analysis_block(self) -> None:
        out = _render()
        assert "[文档结构摘要]" in out
        assert "macros=1" in out

    def test_contains_macro_analysis_block(self) -> None:
        out = _render()
        assert "[宏与仿真摘要]" in out
        assert "simulation_status=ok" in out

    def test_contains_embedded_payloads_block(self) -> None:
        out = _render()
        assert "[嵌入载荷]" in out

    def test_contains_ioc_block(self) -> None:
        out = _render()
        assert "[IOC 候选" in out
        assert "evil.example" in out

    def test_contains_vba_block(self) -> None:
        out = _render()
        assert "[VBA 源码摘要" in out
        assert "Auto_Open" in out

    def test_contains_child_verdicts_block(self) -> None:
        out = _render()
        assert "[已知子样本 Verdict]" in out

    def test_contains_action_directive(self) -> None:
        out = _render()
        assert "请基于以上证据产生工具调用或最终结构化推断" in out


# ---------------------------------------------------------------------------
# Security: untrusted content is wrapped in delimiter tags
# ---------------------------------------------------------------------------


class TestUntrustedContentWrapping:
    """IOC and VBA blocks must be enclosed in untrusted_sample_content tags."""

    def test_ioc_wrapped_in_delimiter_tags(self) -> None:
        out = _render()
        ioc_start = out.find("[IOC 候选")
        assert ioc_start != -1
        segment = out[ioc_start:]
        assert OPEN_TAG in segment
        assert CLOSE_TAG in segment
        open_pos = segment.index(OPEN_TAG)
        close_pos = segment.index(CLOSE_TAG)
        assert open_pos < close_pos
        wrapped = segment[open_pos + len(OPEN_TAG) : close_pos]
        assert "evil.example" in wrapped

    def test_vba_wrapped_in_delimiter_tags(self) -> None:
        out = _render()
        vba_start = out.find("[VBA 源码摘要")
        assert vba_start != -1
        segment = out[vba_start:]
        assert OPEN_TAG in segment
        assert CLOSE_TAG in segment
        open_pos = segment.index(OPEN_TAG)
        close_pos = segment.index(CLOSE_TAG)
        assert open_pos < close_pos
        wrapped = segment[open_pos + len(OPEN_TAG) : close_pos]
        assert "Auto_Open" in wrapped


# ---------------------------------------------------------------------------
# Pure-function contract
# ---------------------------------------------------------------------------


class TestPureFunctionContract:
    """render_document_user_prompt is deterministic and side-effect-free."""

    def test_deterministic_output(self) -> None:
        """Same inputs always produce identical output."""
        out1 = _render()
        out2 = _render()
        assert out1 == out2

    def test_returns_string(self) -> None:
        assert isinstance(_render(), str)

    def test_analysis_id_not_in_output_body(self) -> None:
        """analysis_id is reserved for audit; it must not appear in the template body."""
        out = _render(analysis_id="UNIQUE-SENTINEL-XYZ")
        assert "UNIQUE-SENTINEL-XYZ" not in out

    def test_empty_child_verdicts_table_accepted(self) -> None:
        """Empty child_verdicts_table should not raise and section still renders."""
        out = _render(child_verdicts_table="")
        assert "[已知子样本 Verdict]" in out

    def test_populated_child_verdicts_table_appears(self) -> None:
        table = "child-001 | MALICIOUS | PE32"
        out = _render(child_verdicts_table=table)
        assert table in out


# ---------------------------------------------------------------------------
# VBA truncation integration (caller-side contract)
# ---------------------------------------------------------------------------


class TestVbaTruncationIntegration:
    """Callers must pre-truncate VBA with truncate_vba_source; output passes through."""

    def test_truncated_vba_source_passes_through_verbatim(self) -> None:
        """Pre-truncated VBA appears verbatim inside the delimiter block."""
        long_vba = "\n".join(
            [f"Sub Macro_{i}()\n  MsgBox {i}\nEnd Sub" for i in range(200)]
        )
        truncated = truncate_vba_source(long_vba, max_line_len=80, max_lines=100)
        assert "[... truncated after max_lines ...]" in truncated

        out = _render(vba_source_sanitized=truncated)
        assert truncated in out

    def test_short_vba_source_not_truncated_by_render(self) -> None:
        """render_document_user_prompt does not itself truncate; short source survives."""
        short_vba = "Sub Foo()\n  MsgBox 42\nEnd Sub"
        out = _render(vba_source_sanitized=short_vba)
        assert short_vba in out


# ---------------------------------------------------------------------------
# Fixture regression — stable golden snapshot
# ---------------------------------------------------------------------------


class TestFixtureRegression:
    """Fixed inputs produce a stable, assertable output structure."""

    def test_golden_snapshot_block_order(self) -> None:
        """Blocks appear in the documented order per IMPL-GUIDE §💬."""
        out = _render()
        blocks = [
            "[样本元数据]",
            "[格式与分层]",
            "[文档结构摘要]",
            "[宏与仿真摘要]",
            "[嵌入载荷]",
            "[IOC 候选",
            "[VBA 源码摘要",
            "[已知子样本 Verdict]",
        ]
        positions = [out.find(b) for b in blocks]
        assert -1 not in positions, f"Some blocks not found: {blocks}"
        assert positions == sorted(positions), (
            "Template blocks are not in the expected order"
        )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("document_format", "ole2_doc"),
            ("document_tier", "P0"),
            ("document_analysis_compact", "streams=99 macros=5"),
            (
                "macro_analysis_compact",
                "simulation_status=timeout simulation_gaps_count=3",
            ),
            ("embedded_payloads_compact", "count=2 formats=[PE32, PE32+]"),
        ],
    )
    def test_parametrized_field_appears_in_output(self, field: str, value: str) -> None:
        """Each keyword argument value is reflected in the rendered output."""
        out = _render(**{field: value})
        assert value in out
