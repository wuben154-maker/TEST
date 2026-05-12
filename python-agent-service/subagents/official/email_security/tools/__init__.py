"""Email security analysis tools package.

Re-exports all public tools and helper functions.
Tools that require backend access are plain @tool functions;
use bind_backend(tool, backend_factory) to register with the agent:
    bind_backend(list_uploaded_files, backend_factory)
"""

from ._helpers import (
    BRAND_DOMAINS,
    KNOWN_BRANDS,
    MAX_ATTACHMENT_INLINE_BYTES,
    SUSPICIOUS_TLDS,
    URL_SHORTENERS,
    _BRAND_KEYWORDS,
    _decode_header_value,
    _error_result,
    _normalize_path,
    _resolve_phase4_data,
    bind_backend,
)
from .attachments import (
    _analyze_binary_impl,
    _analyze_html_attachment,
    _audit_office_macro,
    _audit_pdf,
    _compute_entropy,
    _detect_executable_format,
    _inspect_archive,
    analyze_attachment,
    analyze_binary,
    analyze_html_attachment,
    audit_office_macro,
    audit_pdf,
    detect_executable_format,
    inspect_archive,
    scan_attachment_second_pass,
)
from .headers import (
    _check_display_name_spoofing,
    analyze_email_headers,
)
from .parse_eml import (
    _parse_eml_from_bytes,
    list_uploaded_files,
    parse_eml,
)
from .scoring import compute_risk_score
from .image_threats import scan_image_threats
from .ti_open_source import (
    lookup_malwarebazaar,
    lookup_otx,
    lookup_threatfox,
    lookup_urlhaus,
)
from .rdap import rdap_lookup
from .sandbox_fetch import fetch_url_metadata, render_url_fingerprint
from .enrich_orchestrator import run_enrich_phase
from .urls_body import (
    _check_typosquat,
    _enhance_url_analysis,
    _extract_urls_from_html,
    _extract_urls_regex,
    _has_mixed_scripts,
    _scan_images_for_qr,
    _url_sanitize_technical_proofs,
    analyze_all_urls,
    analyze_url_tool,
    detect_prompt_injection,
    extract_urls_tool,
    scan_body_threats,
    scan_quishing,
    score_strong_social_engineering,
    score_social_engineering,
    url_sanitize_tool,
)

__all__ = [
    "BRAND_DOMAINS",
    "KNOWN_BRANDS",
    "MAX_ATTACHMENT_INLINE_BYTES",
    "SUSPICIOUS_TLDS",
    "URL_SHORTENERS",
    "_BRAND_KEYWORDS",
    "_analyze_binary_impl",
    "_analyze_html_attachment",
    "_audit_office_macro",
    "_audit_pdf",
    "_check_display_name_spoofing",
    "_check_typosquat",
    "_compute_entropy",
    "_decode_header_value",
    "_detect_executable_format",
    "_enhance_url_analysis",
    "_error_result",
    "_extract_urls_from_html",
    "_extract_urls_regex",
    "_has_mixed_scripts",
    "_inspect_archive",
    "_normalize_path",
    "_parse_eml_from_bytes",
    "_resolve_phase4_data",
    "_scan_images_for_qr",
    "bind_backend",
    "_url_sanitize_technical_proofs",
    # --- Tools requiring backend (use bind_backend(tool, factory) before registering) ---
    "analyze_attachment",
    "analyze_binary",
    "analyze_html_attachment",
    "audit_office_macro",
    "audit_pdf",
    "detect_executable_format",
    "inspect_archive",
    "list_uploaded_files",
    "parse_eml",
    "scan_attachment_second_pass",
    "scan_image_threats",
    "scan_quishing",
    # --- Stateless tools (no backend needed) ---
    "analyze_all_urls",
    "analyze_email_headers",
    "analyze_url_tool",
    "compute_risk_score",
    "detect_prompt_injection",
    "extract_urls_tool",
    "scan_body_threats",
    # --- Optional enrich tools (networked; best-effort) ---
    "lookup_urlhaus",
    "lookup_malwarebazaar",
    "lookup_threatfox",
    "lookup_otx",
    "rdap_lookup",
    "fetch_url_metadata",
    "render_url_fingerprint",
    "run_enrich_phase",
    "score_strong_social_engineering",
    "score_social_engineering",
    "url_sanitize_tool",
]

