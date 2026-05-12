"""Dispatch hosted-code analysis by inferred language."""

from __future__ import annotations

from .code_language import infer_hosted_language
from .jsp_sinks import scan_jsp_sinks
from .js_html_sinks import scan_js_html_sinks
from .models import Finding
from .php_sinks import scan_php_sinks
from .python_sinks import scan_python_sinks
from .aspx_sinks import scan_aspx_sinks


def scan_hosted_code(content: str) -> tuple[list[Finding], bool, str]:
    """
    Run the sink scanner for the primary hosted language.

    Returns:
        findings, ast_ok, language label (empty if nothing run).
    """
    lang = infer_hosted_language(content)
    if lang == "php":
        return scan_php_sinks(content)
    if lang == "jsp":
        return scan_jsp_sinks(content)
    if lang == "python":
        return scan_python_sinks(content)
    if lang == "aspx":
        return scan_aspx_sinks(content)
    if lang in ("html", "javascript"):
        return scan_js_html_sinks(content)
    return [], False, ""
