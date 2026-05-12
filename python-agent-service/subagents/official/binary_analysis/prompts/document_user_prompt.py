"""Document-mode LLM analysis-pack user prompt renderer (C12, FR-08 AC-1).

This module ships a single pure function :func:`render_document_user_prompt`
that assembles the structured LLM analysis-pack for document-borne malware
analysis (e2e02).

The function is intentionally side-effect-free (no I/O, no state mutation) so
it can be unit-tested without any infrastructure and called repeatedly from the
orchestration layer without concern for hidden coupling.

Design notes (ADR-DOC-10):
- The template mirrors the §💬 specification in IMPL-GUIDE v0.2 verbatim.
- ``vba_source_sanitized`` is expected to be pre-processed by
  :func:`~prompts.sanitize.truncate_vba_source` before being
  passed here; the function does NOT silently re-truncate.
- All untrusted strings (``ioc_candidates_sanitized``, ``vba_source_sanitized``)
  are wrapped in ``<untrusted_sample_content>`` / ``</untrusted_sample_content>``
  delimiter tags by the template — callers MUST sanitize them first via
  :func:`~prompts.sanitize.sanitize`.
"""

from __future__ import annotations

_TEMPLATE = """\
[样本元数据]
{metadata_compact_json}

[格式与分层]
document_format={document_format}
document_tier={document_tier}

[文档结构摘要]
{document_analysis_compact}

[宏与仿真摘要]
{macro_analysis_compact}

[嵌入载荷]
{embedded_payloads_compact}

[IOC 候选（经 sanitize 消毒）]
<untrusted_sample_content>
{ioc_candidates_sanitized}
</untrusted_sample_content>

[VBA 源码摘要（≤ 400 tokens / 模块）]
<untrusted_sample_content>
{vba_source_sanitized}
</untrusted_sample_content>

[已知子样本 Verdict]
{child_verdicts_table}

请基于以上证据产生工具调用或最终结构化推断。"""


def render_document_user_prompt(
    analysis_id: str,
    metadata: str,
    document_format: str,
    document_tier: str,
    document_analysis_compact: str,
    macro_analysis_compact: str,
    embedded_payloads_compact: str,
    ioc_candidates_sanitized: str,
    vba_source_sanitized: str,
    child_verdicts_table: str,
) -> str:
    """Render the structured LLM analysis-pack for document-mode analysis.

    Assembles the 10-field user prompt consumed by :func:`analyst_graph.build_binary_analyst_agent`
    when the sample is identified as a document-borne carrier (FR-08 AC-1 / ADR-DOC-10).
    The template follows the §💬 specification in IMPL-GUIDE v0.2 exactly.

    Args:
        analysis_id: ULID of the current analysis session (reserved for future
            per-analysis correlation; not interpolated into the template body but
            kept in the signature for auditability).
        metadata: JSON-serialised compact sample metadata (sha256, size, mime_type …).
            Must be pre-sanitized by the caller.
        document_format: :class:`~schema.document_enums.DocumentFormat`
            string value (e.g. ``"ooxml_docm"``).
        document_tier: Triage tier string (``"P0"``, ``"P1"``, or ``"P2"``).
        document_analysis_compact: Compact text summary of document structural
            analysis indicators (macro count, embedded objects, stream entropy …).
        macro_analysis_compact: Compact text summary of macro / VBA simulation
            results including ``simulation_status`` and ``simulation_gaps_count``.
        embedded_payloads_compact: Compact text summary of extracted embedded
            payloads (format, sha256, size, ``child_sample_id`` …).
        ioc_candidates_sanitized: IOC candidates already passed through
            :func:`~prompts.sanitize.sanitize`.  Wrapped in
            ``<untrusted_sample_content>`` tags by the template.
        vba_source_sanitized: VBA source already passed through
            :func:`~prompts.sanitize.truncate_vba_source` and
            :func:`~prompts.sanitize.sanitize`.  Wrapped in
            ``<untrusted_sample_content>`` tags by the template.
        child_verdicts_table: Markdown-style table of already-known child sample
            verdicts from completed sub-analyses (``child_sample_id | verdict | …``).
            Empty string when no child analyses have completed yet.

    Returns:
        Fully rendered user prompt string ready for direct injection into the LLM
        context as a ``HumanMessage`` or system-turn append.
    """
    _ = analysis_id  # reserved for future per-analysis audit correlation
    return _TEMPLATE.format(
        metadata_compact_json=metadata,
        document_format=document_format,
        document_tier=document_tier,
        document_analysis_compact=document_analysis_compact,
        macro_analysis_compact=macro_analysis_compact,
        embedded_payloads_compact=embedded_payloads_compact,
        ioc_candidates_sanitized=ioc_candidates_sanitized,
        vba_source_sanitized=vba_source_sanitized,
        child_verdicts_table=child_verdicts_table,
    )


__all__ = ["render_document_user_prompt"]
