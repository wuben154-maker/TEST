"""Allowed `indicator_type` values for Schema v1.1.0 document buckets (IR-DOC-02).

Each frozenset defines the exhaustive set of legal `indicator_type` strings for
the corresponding evidence-chain bucket added in C1.  The EvidenceChainStore
append entry-point (C2) validates incoming Indicators against these sets and
raises ``ValueError`` for any value not present.

This file is the single source of truth for indicator_type enumeration in the
v1.1 document buckets.  Downstream consumers (C2 / C5 / C9 / C11) MUST import
from here rather than duplicating the sets inline.

References: IMPL-GUIDE §📦, IR-DOC-02, FR-09 AC-3.
"""

from __future__ import annotations

DOC_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {
        "ole_structure",
        "ooxml_part",
        "trigger",
        "dde_field",
        "remote_template_ref",
        "document_metadata",
        "xfa_form",
        "pdf_object_tree",
        "pdf_action_chain",
        "pdf_keyword_summary",
        "pdf_js_analysis",
        "document_parser_failed",
    }
)
"""Legal ``indicator_type`` values for the ``document_analysis`` bucket.

Covers: OLE2 / OOXML structural elements, macro triggers, DDE fields,
remote template injection references, document metadata, XFA forms,
PDF object trees, action chains, keyword/JavaScript summaries, parser failure
records.
"""

MACRO_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {
        "vba_module",
        "vba_module_hash",
        "xl4_macro",
        "xl4_deobfuscated",
        "macro_action_call",
        "vba_simulation_gap",
        "vba_simulation_timeout",
        "macro_simulation_status",
    }
)
"""Legal ``indicator_type`` values for the ``macro_analysis`` bucket.

Covers: VBA / XL4 macro source, deobfuscated XL4, action call records,
simulation gaps and timeouts, overall simulation status.
"""

EMBEDDED_PAYLOADS_TYPES: frozenset[str] = frozenset(
    {
        "embedded_ole_object",
        "pdf_embedded_file",
        "onenote_file_data_store",
        "rtf_obj_data",
        "child_sample_ref",
        "recursion_depth_exceeded",
    }
)
"""Legal ``indicator_type`` values for the ``embedded_payloads`` bucket.

Covers: OLE embedded objects, PDF embedded files, OneNote FileDataStoreObjects,
RTF object data, child sample references for recursive analysis,
recursion depth exceeded markers.
"""

DELIVERY_CHAIN_DOC_TYPES: frozenset[str] = frozenset(
    {
        "parent_child_link",
        "polyglot_decision",
        "delivery_chain_node",
        "delivery_chain_root",
    }
)
"""Legal ``indicator_type`` values for the ``delivery_chain_doc`` bucket.

Covers: parent–child sample links, polyglot format decisions,
individual nodes and the root node of the delivery-chain tree.
"""

#: Union of all v1.1 document-bucket indicator types (convenience constant).
ALL_DOC_INDICATOR_TYPES: frozenset[str] = (
    DOC_ANALYSIS_TYPES
    | MACRO_ANALYSIS_TYPES
    | EMBEDDED_PAYLOADS_TYPES
    | DELIVERY_CHAIN_DOC_TYPES
)
