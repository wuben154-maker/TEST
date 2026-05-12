"""Phase 4 tools: attachment analysis (PDF, archive, Office, HTML, binary).

Provides both per-type tools and a unified `analyze_attachment` that routes
analysis by file extension / content type, reducing the number of tools the
LLM agent must choose from. All tools use runtime injection via ToolRuntime.

All analyzers are self-contained — no external PhishGuard dependency.
"""

from __future__ import annotations

import io
import math
import re
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from ._helpers import _resolve_phase4_data, logger
from .urls_body import _scan_images_for_qr
from .policy import normalize_url  # noqa: PLC0415

_PE_MZ = b"MZ"
_ELF_SIG = b"\x7fELF"
_MACHO_SIGS = frozenset(
    {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"}
)


def _detect_executable_format(data: bytes) -> Literal["PE", "ELF", "MACHO", ""]:
    """Return ``PE``, ``ELF``, ``MACHO`` if data looks like that format; else ``""``."""
    if len(data) < 4:
        return ""
    if data[:2] == _PE_MZ:
        return "PE"
    if data[:4] == _ELF_SIG:
        return "ELF"
    if data[:4] in _MACHO_SIGS:
        return "MACHO"
    return ""


_PDF_RISKY_KEYWORDS: list[tuple[bytes, str]] = [
    (b"/JavaScript", "JavaScript in PDF"),
    (b"/JS ", "JS object in PDF"),
    (b"/JS\n", "JS object in PDF"),
    (b"/OpenAction", "OpenAction (auto action)"),
    (b"/AA ", "Additional Actions"),
    (b"/AA\n", "Additional Actions"),
    (b"/URI ", "URI (auto external link)"),
]
_PDF_HEAD_MAX = 256 * 1024


def _audit_pdf(data: bytes, filename: str = "attachment.pdf") -> dict[str, Any]:
    """Inspect PDF for risky objects; return attachment_risks entry."""
    head = data[:_PDF_HEAD_MAX]
    findings: list[str] = []
    for pattern, label in _PDF_RISKY_KEYWORDS:
        if pattern in head:
            findings.append(label)

    if not findings:
        return {
            "filename": filename,
            "risk": "LOW",
            "detail": "No risky PDF objects detected in header.",
            "findings": [],
        }

    high = [f for f in findings if "OpenAction" in f or "JS" in f or "JavaScript" in f]
    risk = "CRITICAL" if len(high) >= 2 else "HIGH" if high else "MEDIUM"
    detail = "PDF contains: " + "; ".join(findings[:5])
    if len(findings) > 5:
        detail += f" (+{len(findings) - 5} more)"
    return {"filename": filename, "risk": risk, "detail": detail, "findings": findings}


_RLO = "\u202e"
_RISKY_EXTENSIONS = frozenset({".exe", ".scr", ".vbs", ".bat", ".cmd", ".ps1", ".js", ".jar", ".com"})


def _has_double_suffix(name: str) -> bool:
    """Detect ``invoice.pdf.exe`` style double extension."""
    suffixes = Path(name).suffixes
    return len(suffixes) >= 2 and suffixes[-1].lower() in _RISKY_EXTENSIONS


def _inspect_zip(data: bytes, filename: str = "archive.zip") -> dict[str, Any]:
    """List zip contents and flag double extension, RLO, risky ext."""
    findings: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as z:
            for info in z.infolist():
                n = info.filename.rstrip("/")
                if not n or n.endswith("/"):
                    continue
                if _RLO in n:
                    findings.append(f"RLO in name: {n[:80]}")
                if _has_double_suffix(n):
                    findings.append(f"Double suffix: {n}")
                if Path(n).suffix.lower() in _RISKY_EXTENSIONS:
                    findings.append(f"Risky extension: {n}")
    except Exception as exc:  # noqa: BLE001
        return {
            "filename": filename,
            "risk": "MEDIUM",
            "detail": f"Zip inspection error: {exc}",
            "findings": [],
        }

    if not findings:
        return {
            "filename": filename,
            "risk": "LOW",
            "detail": "Archive content list OK; no double extension/RLO/risky ext.",
            "findings": [],
        }
    risk = "CRITICAL" if any("Double suffix" in f or "RLO" in f for f in findings) else "HIGH"
    detail = "; ".join(findings[:5])
    if len(findings) > 5:
        detail += f" (+{len(findings) - 5})"
    return {"filename": filename, "risk": risk, "detail": detail, "findings": findings}


def _inspect_archive(data: bytes, filename: str) -> dict[str, Any]:
    """Inspect zip or rar by extension; otherwise try zip."""
    lower = filename.lower()
    if lower.endswith(".rar"):
        try:
            import rarfile  # noqa: PLC0415

            with rarfile.RarFile(io.BytesIO(data), "r") as r:
                findings: list[str] = []
                for info in r.infolist():
                    n = (info.filename or "").rstrip("/")
                    if not n or n.endswith("/"):
                        continue
                    if _RLO in n:
                        findings.append(f"RLO: {n[:80]}")
                    if _has_double_suffix(n):
                        findings.append(f"Double suffix: {n}")
                    if Path(n).suffix.lower() in _RISKY_EXTENSIONS:
                        findings.append(f"Risky ext: {n}")
                if not findings:
                    return {"filename": filename, "risk": "LOW", "detail": "RAR list OK.", "findings": []}
                risk = "CRITICAL" if any("Double" in f or "RLO" in f for f in findings) else "HIGH"
                return {
                    "filename": filename,
                    "risk": risk,
                    "detail": "; ".join(findings[:5]),
                    "findings": findings,
                }
        except ImportError:
            logger.debug("rarfile not installed; falling back to zip inspection")
        except Exception as exc:  # noqa: BLE001
            return {"filename": filename, "risk": "MEDIUM", "detail": str(exc), "findings": []}
    return _inspect_zip(data, filename)


_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_HIGH_RISK_MACRO_PATTERNS = (
    "AutoOpen",
    "Shell",
    "WScript.Shell",
    "CreateObject",
    "Run(",
    "cmd.exe",
    "powershell",
)


def _audit_office_macro(data: bytes, filename: str = "attachment.docx") -> dict[str, Any]:
    """Extract VBA and flag AutoOpen/Shell etc. Requires oletools."""
    if len(data) < 8 or data[:8] != _OLE_SIGNATURE:
        return {"filename": filename, "risk": "LOW", "detail": "Not an OLE file; macro check skipped.", "findings": []}
    try:
        from oletools.olevba import VBA_Parser  # noqa: PLC0415

        parser = VBA_Parser(filename, data=data)
        findings: list[str] = []
        try:
            for code in parser.extract_macros() or []:
                src = (code[3] or "").lower()
                for pat in _HIGH_RISK_MACRO_PATTERNS:
                    if pat.lower() in src:
                        findings.append(f"VBA contains: {pat}")
                        break
            if parser.detect_vba_macros() and not findings:
                findings.append("VBA macros present; no high-risk patterns matched.")
        finally:
            parser.close()
        if not findings:
            return {"filename": filename, "risk": "LOW", "detail": "OLE file inspected; no VBA or no high-risk patterns.", "findings": []}
        risk = (
            "HIGH"
            if any(
                "Shell" in f or "AutoOpen" in f or "cmd.exe" in f or "powershell" in f
                for f in findings
            )
            else "MEDIUM"
        )
        detail = "; ".join(findings[:5])
        if len(findings) > 5:
            detail += f" (+{len(findings) - 5})"
        return {"filename": filename, "risk": risk, "detail": detail, "findings": findings}
    except ImportError:
        return {
            "filename": filename,
            "risk": "UNKNOWN",
            "detail": "oletools not installed; Office macro check skipped (analysis_unavailable).",
            "findings": [],
            "analysis_unavailable": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"filename": filename, "risk": "MEDIUM", "detail": f"Office macro inspection error: {exc}", "findings": []}


_HTML_SMUGGLING_CHECKS: list[tuple[str, Callable[[str], bool]]] = [
    (
        "JavaScript Blob creation (potential file download trigger)",
        lambda c: "URL.createObjectURL" in c or "Blob(" in c,
    ),
    ("JavaScript atob() base64 decoding detected", lambda c: bool(re.search(r"atob\s*\(", c))),
    (
        "Auto-download trigger (<a download> or element.click())",
        lambda c: bool(
            re.search(r"\.click\(\)", c) or re.search(r"download\s*=", c, re.IGNORECASE)
        ),
    ),
    ("Dynamic content injection (document.write / innerHTML)", lambda c: "document.write" in c or "innerHTML" in c),
]


def _analyze_html_attachment(data: bytes, filename: str) -> dict[str, Any]:
    """Detect HTML smuggling patterns in HTML file attachments."""
    try:
        content = data.decode("utf-8", errors="replace")
    except Exception:
        return {"filename": filename, "risk": "UNKNOWN", "detail": "Cannot decode HTML.", "findings": []}

    findings: list[str] = []
    for desc, check in _HTML_SMUGGLING_CHECKS:
        if check(content):
            findings.append(desc)

    b64_matches = re.findall(r'["\'][A-Za-z0-9+/]{1000,}={0,2}["\']', content)
    if b64_matches:
        findings.append(f"Large base64 string(s) embedded ({len(b64_matches)} found).")

    risk = "HIGH" if len(findings) >= 3 else ("MEDIUM" if findings else "LOW")
    return {
        "filename": filename,
        "risk": risk,
        "detail": f"HTML smuggling scan: {len(findings)} indicator(s).",
        "findings": findings,
    }


_PE_SUSPICIOUS_IMPORTS = frozenset(
    {
        "virtualalloc",
        "virtualprotect",
        "createremotethread",
        "writeprocessmemory",
        "loadlibrary",
        "getprocaddress",
        "ntcreatethreadex",
        "rtlcreateuserthread",
        "shellexecute",
        "winexec",
        "urldownloadtofile",
        "internetopenurl",
    }
)


def _compute_entropy(data: bytes) -> float:
    """Compute Shannon entropy of a byte sequence (0.0 to 8.0)."""
    if not data:
        return 0.0
    freq: dict[int, int] = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    length = len(data)
    entropy = 0.0
    for count in freq.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 4)


def _analyze_pe(data: bytes) -> dict[str, Any]:
    """Basic PE (Windows executable) analysis: headers, imports, entropy, sections."""
    findings: list[str] = []

    if len(data) < 64:
        return {"file_type": "PE", "risk": "UNKNOWN", "indicators": ["File too small for PE analysis"], "summary": "Truncated PE."}

    if data[:2] != b"MZ":
        return {"file_type": "PE", "risk": "UNKNOWN", "indicators": ["Missing MZ signature"], "summary": "Not a valid PE."}

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0] if len(data) > 0x3F else 0
    if e_lfanew == 0 or e_lfanew + 4 > len(data):
        findings.append("Invalid PE header offset.")
        return {"file_type": "PE", "risk": "MEDIUM", "indicators": findings, "summary": "Malformed PE header."}

    pe_sig = data[e_lfanew : e_lfanew + 4]
    if pe_sig != b"PE\x00\x00":
        findings.append("Invalid PE signature.")
        return {"file_type": "PE", "risk": "MEDIUM", "indicators": findings, "summary": "Malformed PE."}

    if e_lfanew + 24 > len(data):
        findings.append("Truncated COFF header.")
        return {"file_type": "PE", "risk": "MEDIUM", "indicators": findings, "summary": "Truncated PE."}

    coff_offset = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff_offset + 2)[0]
    characteristics = struct.unpack_from("<H", data, coff_offset + 18)[0]

    if characteristics & 0x2000:
        findings.append("DLL (Dynamic Link Library).")
    if characteristics & 0x0002:
        findings.append("Executable image.")

    overall_entropy = _compute_entropy(data)
    if overall_entropy > 7.2:
        findings.append(f"High overall entropy ({overall_entropy}) — likely packed or encrypted.")

    optional_hdr_size = struct.unpack_from("<H", data, coff_offset + 16)[0]
    section_offset = coff_offset + 20 + optional_hdr_size
    for i in range(min(num_sections, 96)):
        sec_start = section_offset + i * 40
        if sec_start + 40 > len(data):
            break
        sec_name = data[sec_start : sec_start + 8].rstrip(b"\x00").decode("ascii", errors="replace")
        raw_size = struct.unpack_from("<I", data, sec_start + 16)[0]
        raw_ptr = struct.unpack_from("<I", data, sec_start + 20)[0]
        sec_chars = struct.unpack_from("<I", data, sec_start + 36)[0]
        is_writable = bool(sec_chars & 0x80000000)
        is_executable = bool(sec_chars & 0x20000000)
        if is_writable and is_executable:
            findings.append(f"Section '{sec_name}' is both writable and executable (W+X).")
        if raw_ptr and raw_size and raw_ptr + raw_size <= len(data):
            sec_entropy = _compute_entropy(data[raw_ptr : raw_ptr + min(raw_size, 65536)])
            if sec_entropy > 7.5:
                findings.append(f"Section '{sec_name}' has high entropy ({sec_entropy}) — possible packing.")

    text_content = data.decode("ascii", errors="ignore").lower()
    suspicious_found: list[str] = []
    for api in _PE_SUSPICIOUS_IMPORTS:
        if api in text_content:
            suspicious_found.append(api)
    if suspicious_found:
        findings.append(f"Suspicious imports: {', '.join(sorted(suspicious_found))}.")

    risk = "LOW"
    if len(findings) >= 4 or overall_entropy > 7.5:
        risk = "CRITICAL"
    elif len(findings) >= 2:
        risk = "HIGH"
    elif findings:
        risk = "MEDIUM"

    return {
        "file_type": "PE",
        "risk": risk,
        "indicators": findings,
        "summary": f"PE analysis: {len(findings)} indicator(s), entropy={overall_entropy}.",
    }


def _analyze_elf(data: bytes) -> dict[str, Any]:
    """Basic ELF (Linux/Unix executable) analysis."""
    findings: list[str] = []

    if len(data) < 16 or data[:4] != b"\x7fELF":
        return {"file_type": "ELF", "risk": "UNKNOWN", "indicators": ["Not a valid ELF"], "summary": "Invalid ELF."}

    ei_class = data[4]
    findings.append(f"{'64-bit' if ei_class == 2 else '32-bit'} ELF.")

    overall_entropy = _compute_entropy(data[: min(len(data), 65536)])
    if overall_entropy > 7.2:
        findings.append(f"High entropy ({overall_entropy}) — possible packing/encryption.")

    if b"UPX!" in data[:4096]:
        findings.append("UPX packer signature detected.")

    risk = "HIGH" if len(findings) >= 2 else "MEDIUM"
    return {
        "file_type": "ELF",
        "risk": risk,
        "indicators": findings,
        "summary": f"ELF analysis: {len(findings)} indicator(s), entropy={overall_entropy}.",
    }


def _analyze_macho(data: bytes) -> dict[str, Any]:
    """Basic Mach-O (macOS executable) analysis."""
    findings: list[str] = []

    overall_entropy = _compute_entropy(data[: min(len(data), 65536)])
    if overall_entropy > 7.2:
        findings.append(f"High entropy ({overall_entropy}) — possible packing/encryption.")

    magic = data[:4]
    if magic in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf"):
        findings.append("Mach-O big-endian.")
    elif magic in (b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
        findings.append("Mach-O little-endian.")

    risk = "HIGH" if len(findings) >= 2 else "MEDIUM"
    return {
        "file_type": "MACHO",
        "risk": risk,
        "indicators": findings,
        "summary": f"Mach-O analysis: {len(findings)} indicator(s), entropy={overall_entropy}.",
    }


def _analyze_binary_impl(data: bytes, filename: str) -> dict[str, Any]:
    """Dispatch binary analysis based on magic bytes."""
    if len(data) < 4:
        return {"file_type": "unknown", "risk": "UNKNOWN", "indicators": ["File too small"], "summary": "Cannot analyze."}

    if data[:2] == b"MZ":
        return _analyze_pe(data)
    if data[:4] == b"\x7fELF":
        return _analyze_elf(data)
    if data[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
        return _analyze_macho(data)

    overall_entropy = _compute_entropy(data[: min(len(data), 65536)])
    findings: list[str] = [f"Unknown binary format for '{filename}'."]
    if overall_entropy > 7.0:
        findings.append(f"High entropy ({overall_entropy}).")

    return {
        "file_type": "unknown",
        "risk": "MEDIUM" if overall_entropy > 7.0 else "LOW",
        "indicators": findings,
        "summary": f"Generic binary: entropy={overall_entropy}.",
    }


@tool
def analyze_binary(
    file_path: Annotated[str, "Path to binary file (under /uploaded/)."],
    filename: Annotated[str, "Display name."] = "binary",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Deep binary analysis for PE/ELF/Mach-O executables: header parsing, section entropy, import table scanning, packing detection. Provide file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {"file_type": "unknown", "risk": "UNKNOWN", "indicators": [err or "No data"], "summary": "Cannot analyze."}
    return _analyze_binary_impl(data, filename)


@tool
def detect_executable_format(
    file_path: Annotated[str, "Path to file (under /uploaded/)."],
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Detect whether a file is a PE/ELF/Mach-O executable by magic bytes. Input: file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {"format": "", "detail": err or "No data"}
    fmt = _detect_executable_format(data)
    return {"format": fmt, "detail": f"Detected format: {fmt}" if fmt else "No executable format detected."}


@tool
def audit_pdf(
    file_path: Annotated[str, "Path to PDF file (under /uploaded/)."],
    filename: Annotated[str, "Original filename."] = "attachment.pdf",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Inspect a PDF attachment for risky objects (JavaScript/OpenAction). Input: file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {"filename": filename, "risk": "UNKNOWN", "detail": err or "No data", "findings": []}
    return _audit_pdf(data, filename)


@tool
def inspect_archive(
    file_path: Annotated[str, "Path to archive file (under /uploaded/)."],
    filename: Annotated[str, "Original filename."] = "archive.zip",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Inspect an archive (zip/rar) for risky filenames (RLO/double extension). Input: file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {"filename": filename, "risk": "UNKNOWN", "detail": err or "No data", "findings": []}
    return _inspect_archive(data, filename)


@tool
def audit_office_macro(
    file_path: Annotated[str, "Path to Office file (under /uploaded/)."],
    filename: Annotated[str, "Original filename."] = "attachment.docx",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Inspect an Office attachment for VBA macros (OLE). Input: file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {"filename": filename, "risk": "UNKNOWN", "detail": err or "No data", "findings": []}
    return _audit_office_macro(data, filename)


@tool
def analyze_html_attachment(
    file_path: Annotated[str, "Path to HTML file (under /uploaded/)."],
    filename: Annotated[str, "Original filename."] = "attachment.html",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Analyze an HTML attachment for smuggling indicators. Input: file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {"filename": filename, "risk": "UNKNOWN", "detail": err or "No data", "findings": []}
    return _analyze_html_attachment(data, filename)


_PDF_EXTENSIONS = frozenset({".pdf"})
_ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"})
_OFFICE_EXTENSIONS = frozenset({".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".pptm", ".docm"})
_HTML_EXTENSIONS = frozenset({".html", ".htm", ".svg", ".xhtml"})
_DISK_IMAGE_EXTENSIONS = frozenset({".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".dmg"})
_SCRIPT_EXTENSIONS = frozenset(
    {".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".lnk", ".scr", ".com", ".jar"}
)
_EXECUTABLE_EXTENSIONS = frozenset({".exe", ".dll", ".sys", ".msi", ".cpl", ".ocx"})
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"})


def _classify_attachment_tier(ext: str, ct: str, fname_lower: str) -> str | None:
    """Map an attachment's ext + MIME to a delegation tier.

    Tiers mirror the email_security AGENT.md S4 contract:
    - ``tier1``: direct-execution / scripts / executables → MUST delegate to binary-analysis.
    - ``tier2``: Office docs, PDFs, archives, disk images → MUST delegate to binary-analysis.
    - ``tier3``: stealth-friendly types (images, html, eml, txt) → SHOULD delegate.
    - ``None``: classification ambiguous — let the agent decide from prompt rules.

    The output is consumed by ``_with_attachment_evidence`` to populate the
    ``needs_binary_analysis`` flag so the email-security agent's MUST-delegate
    triggers fire even when the content-based scan returned LOW risk.
    """
    if ext in _EXECUTABLE_EXTENSIONS or ext in _SCRIPT_EXTENSIONS:
        return "tier1"
    if ext in _PDF_EXTENSIONS or "pdf" in ct:
        return "tier2"
    if (
        ext in _OFFICE_EXTENSIONS
        or "officedocument" in ct
        or "msword" in ct
        or "ms-excel" in ct
        or "ms-powerpoint" in ct
    ):
        return "tier2"
    if ext in _ARCHIVE_EXTENSIONS or fname_lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        return "tier2"
    if ext in _DISK_IMAGE_EXTENSIONS:
        return "tier2"
    if ext in _HTML_EXTENSIONS or ext in _IMAGE_EXTENSIONS or ext in {".eml", ".msg", ".txt"}:
        return "tier3"
    return None
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"})


def _second_pass_scan_impl(data: bytes, filename: str, content_type: str) -> dict[str, Any]:
    """Second-pass scan for any attachment; returns unified dict."""
    ext = Path(filename).suffix.lower()
    fname_lower = filename.lower()
    ct = content_type.lower()

    if len(data) >= 4:
        fmt = _detect_executable_format(data)
        if fmt:
            return _analyze_binary_impl(data, filename)

    if ext in _IMAGE_EXTENSIONS or ct.startswith("image/"):
        qr_results = _scan_images_for_qr([data])
        indicators = [r["url"] for r in qr_results if r.get("url")]
        risk = "HIGH" if indicators else "LOW"
        summary = (
            f"Image second-pass: {len(indicators)} QR/URL(s) decoded."
            if indicators
            else "Image second-pass: no QR codes or suspicious URLs."
        )
        return {"file_type": "image", "risk": risk, "indicators": indicators, "summary": summary}

    if ext in _PDF_EXTENSIONS or "pdf" in ct:
        result = _audit_pdf(data, filename)
        return {
            "file_type": "PDF",
            "risk": result.get("risk", "UNKNOWN"),
            "indicators": result.get("findings", []),
            "summary": result.get("detail", ""),
        }

    if ext in _ARCHIVE_EXTENSIONS or fname_lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        result = _inspect_archive(data, filename)
        return {
            "file_type": "archive",
            "risk": result.get("risk", "UNKNOWN"),
            "indicators": result.get("findings", []),
            "summary": result.get("detail", ""),
        }

    if ext in _OFFICE_EXTENSIONS or "officedocument" in ct or "msword" in ct:
        result = _audit_office_macro(data, filename)
        return {
            "file_type": "office",
            "risk": result.get("risk", "UNKNOWN"),
            "indicators": result.get("findings", []),
            "summary": result.get("detail", ""),
        }

    if ext in _HTML_EXTENSIONS or "html" in ct or "svg" in ct:
        result = _analyze_html_attachment(data, filename)
        return {
            "file_type": "html",
            "risk": result.get("risk", "UNKNOWN"),
            "indicators": result.get("findings", []),
            "summary": result.get("detail", ""),
        }

    entropy = _compute_entropy(data[: min(len(data), 65536)])
    risk = "MEDIUM" if entropy > 7.0 else "LOW"
    indicators = [f"High entropy ({entropy:.2f})"] if entropy > 7.0 else []
    return {
        "file_type": "unknown",
        "risk": risk,
        "indicators": indicators,
        "summary": f"Unknown type (ext={ext!r}), entropy={entropy:.2f}.",
    }


@tool
def scan_attachment_second_pass(
    file_path: Annotated[str, "Path to file for second-pass scan (under /uploaded/)."],
    filename: Annotated[str, "Original filename with extension."] = "attachment",
    content_type: Annotated[str, "MIME content type, e.g. 'application/pdf'."] = "",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Second-pass security scan for any attachment (executable, image, PDF, archive, Office, HTML, or unknown). Input: file_path, plus filename and content_type. Output: file_type, risk, indicators, summary."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        return {
            "file_type": "unknown",
            "risk": "UNKNOWN",
            "indicators": [err or "No data"],
            "summary": "Second-pass scan could not be performed.",
        }
    return _second_pass_scan_impl(data, filename, content_type)


@tool
def analyze_attachment(
    file_path: Annotated[str, "Path to file for standalone analysis (under /uploaded/)."],
    filename: Annotated[str, "Original filename with extension."] = "attachment",
    content_type: Annotated[str, "MIME content type, e.g. 'application/pdf'."] = "",
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Analyze an email attachment for security risks. Automatically routes to the correct analyzer based on filename extension and content_type: PDF (JavaScript, OpenAction), archives (double extensions, RLO), Office docs (VBA macros), HTML (smuggling), or executable detection (PE/ELF/Mach-O). Provide file_path."""
    data, err = _resolve_phase4_data(file_path, backend_factory, runtime)
    if err or data is None:
        out = _att_result(filename, content_type, "UNKNOWN", err or "No data")
        out["evidence"] = [
            {
                "signal": "attachment_analysis_unavailable",
                "severity": "LOW",
                "confidence": "high",
                "artifact": {"type": "file", "value": file_path, "context": {"filename": filename}},
                "source": "analyze_attachment",
                "detail": out.get("detail", "analysis unavailable"),
                "limitations": ["analysis_unavailable"],
            }
        ]
        return out

    ext = Path(filename).suffix.lower()
    fname_lower = filename.lower()
    ct = content_type.lower()

    if ext in _PDF_EXTENSIONS or "pdf" in ct:
        result = _audit_pdf(data, filename)
        result.setdefault("content_type", content_type)
        return _with_attachment_evidence(result, file_path=file_path, filename=filename, content_type=content_type)

    if ext in _ARCHIVE_EXTENSIONS or fname_lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        result = _inspect_archive(data, filename)
        result.setdefault("content_type", content_type)
        return _with_attachment_evidence(result, file_path=file_path, filename=filename, content_type=content_type)

    if ext in _OFFICE_EXTENSIONS or "officedocument" in ct or "msword" in ct:
        result = _audit_office_macro(data, filename)
        result.setdefault("content_type", content_type)
        return _with_attachment_evidence(result, file_path=file_path, filename=filename, content_type=content_type)

    if ext in _HTML_EXTENSIONS or "html" in ct or "svg" in ct:
        result = _analyze_html_attachment(data, filename)
        result.setdefault("content_type", content_type)
        return _with_attachment_evidence(result, file_path=file_path, filename=filename, content_type=content_type)

    fmt = _detect_executable_format(data) if len(data) >= 4 else ""
    if fmt:
        result = {
            "filename": filename,
            "content_type": content_type,
            "analysis_type": "executable",
            "format_detected": fmt,
            "risk": "HIGH",
            "detail": f"Executable format ({fmt}) detected. Delegate to scan_attachment_second_pass for deep analysis.",
            "findings": [f"Executable format: {fmt}"],
            "needs_binary_analysis": True,
        }
        return _with_attachment_evidence(result, file_path=file_path, filename=filename, content_type=content_type)

    entropy = _compute_entropy(data[: min(len(data), 65536)])
    risk = "MEDIUM" if entropy > 7.0 else "LOW"
    findings = [f"High entropy ({entropy:.2f})"] if entropy > 7.0 else []
    logger.debug("analyze_attachment: unknown type '%s', entropy=%.2f", ext, entropy)
    result = {
        "filename": filename,
        "content_type": content_type,
        "analysis_type": "unknown",
        "risk": risk,
        "detail": f"Unknown attachment type (ext={ext!r}), entropy={entropy:.2f}.",
        "findings": findings,
    }
    return _with_attachment_evidence(result, file_path=file_path, filename=filename, content_type=content_type)


def _att_result(filename: str, content_type: str, risk: str, detail: str) -> dict[str, Any]:
    return {"filename": filename, "content_type": content_type, "risk": risk, "detail": detail, "findings": []}


def _with_attachment_evidence(
    result: dict[str, Any],
    *,
    file_path: str,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    fname_lower = filename.lower()
    ext = Path(filename).suffix.lower()
    ct_lower = content_type.lower()
    tier = _classify_attachment_tier(ext, ct_lower, fname_lower)
    if tier is not None:
        result.setdefault("attachment_tier", tier)
    if tier in ("tier1", "tier2"):
        # Force the MUST-delegate trigger from email_security AGENT.md S4 even
        # when the content-based scan returned LOW risk: PDF / Office / archive
        # / disk-image / script / executable types should always reach the
        # binary-analysis subagent when budget permits.
        result["needs_binary_analysis"] = True

    risk = str(result.get("risk") or "UNKNOWN")
    findings = result.get("findings") or []
    evidence: list[dict[str, Any]] = [
        {
            "signal": f"attachment_primary_risk_{risk.lower()}",
            "severity": "CRITICAL" if risk == "CRITICAL" else ("HIGH" if risk == "HIGH" else ("MEDIUM" if risk == "MEDIUM" else "LOW")),
            "confidence": "high",
            "artifact": {"type": "file", "value": file_path, "context": {"filename": filename, "content_type": content_type}},
            "source": "analyze_attachment",
            "detail": str(result.get("detail") or ""),
            "details": {"findings": findings[:20]},
        }
    ]
    for f in findings[:50]:
        if not isinstance(f, str):
            continue
        if "http://" in f or "https://" in f:
            for u in re.findall(r"https?://[^\s<>\"]+", f):
                evidence.append(
                    {
                        "signal": "attachment_embedded_url_observed",
                        "severity": "MEDIUM",
                        "confidence": "medium",
                        "artifact": {"type": "url", "value": normalize_url(u), "context": {"filename": filename}},
                        "source": "analyze_attachment",
                        "detail": f"URL observed in attachment finding: {u}",
                    }
                )
    result["evidence"] = evidence
    return result

