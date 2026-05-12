"""run_peepdf.py — PDF structure and trigger extraction worker (FR-03 AC-6/7).

Invocation (by host via SandboxClient)::

    python run_peepdf.py --input <json_path>

Input JSON::

    {
        "sample_path": "/workspace/<aid>/sample.pdf"
    }

Stdout JSON contract::

    {
        "object_tree": [
            {
                "obj_id": 1,
                "obj_type": "dictionary",
                "contains_js": false
            }
        ],
        "triggers": [
            {
                "type": "OpenAction",
                "action_type": "JavaScript",
                "js_preview": "<first 256 chars>"
            }
        ],
        "embedded_files": [
            {
                "name": "payload.exe",
                "sha256": "<hex64>",
                "size_bytes": 4096,
                "suggested_format": "pe",
                "extracted_to": "/workspace/<aid>/children/pdf_embedded_001_<sha16>.bin",
                "materialized": true
            }
        ],
        "action_chains": [
            {
                "chain": ["OpenAction", "GoTo", "JavaScript"]
            }
        ],
        "xfa_form": {
            "present": false,
            "script_count": 0
        },
        "keyword_summary": {
            "keywords": {},
            "risk_counts": {"high": 0, "medium": 0, "low": 0},
            "structure": {}
        },
        "js_analysis": {
            "blocks": [],
            "markers": {},
            "has_shellcode_markers": false,
            "has_obfuscation_markers": false
        },
        "uris": [],
        "submit_targets": []
    }

On peepdf import failure the result is::

    {"error": "peepdf not available: ...", "object_tree": [], "triggers": [],
     "embedded_files": [], "action_chains": [], "xfa_form": {"present": false, "script_count": 0}}

Security (NFR-04 / IR-DOC-01)
------------------------------
peepdf performs static PDF parsing — it never launches Adobe Reader or executes
embedded JavaScript.  This worker is the only location allowed to import peepdf;
host code must not import it directly (CI enforces this via AST scan).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_EMPTY_RESULT: dict = {
    "object_tree": [],
    "triggers": [],
    "embedded_files": [],
    "action_chains": [],
    "xfa_form": {"present": False, "script_count": 0},
    "keyword_summary": {
        "keywords": {},
        "risk_counts": {"high": 0, "medium": 0, "low": 0},
        "structure": {},
    },
    "js_analysis": {
        "blocks": [],
        "markers": {},
        "has_shellcode_markers": False,
        "has_obfuscation_markers": False,
    },
    "uris": [],
    "submit_targets": [],
}

_PDF_KEYWORD_RISK: dict[str, str] = {
    "/JS": "high",
    "/JavaScript": "high",
    "/AA": "high",
    "/OpenAction": "high",
    "/Launch": "high",
    "/JBIG2Decode": "high",
    "/EmbeddedFile": "medium",
    "/RichMedia": "medium",
    "/AcroForm": "medium",
    "/XFA": "medium",
    "/SubmitForm": "medium",
    "/ObjStm": "low",
    "/URI": "low",
}

_JS_MARKER_PATTERNS: dict[str, str] = {
    "heap_spray": r"(%u[0-9a-fA-F]{4}){4,}",
    "nop_sled": r"(\\x90){8,}|(%u9090){4,}",
    "unescape_chain": r"unescape\s*\(",
    "shellcode_var": r"shellcode|payload|sc\s*=\s*[\"']",
    "fromcharcode": r"String\.fromCharCode",
    "eval_call": r"eval\s*\(",
    "activex": r"new\s+ActiveXObject",
    "util_printf": r"util\.printf",
    "collab_geticon": r"collab\.getIcon",
}

_SHELLCODE_MARKERS: frozenset[str] = frozenset(
    {"heap_spray", "nop_sled", "shellcode_var", "util_printf", "collab_geticon"}
)
_OBFUSCATION_MARKERS: frozenset[str] = frozenset(
    {"unescape_chain", "fromcharcode", "eval_call", "activex"}
)


def _empty_result_with(scan: dict | None = None, error: str | None = None) -> dict:
    """Return a fresh result object so nested defaults are never shared."""
    result = json.loads(json.dumps(_EMPTY_RESULT))
    if scan:
        result.update(scan)
    if error:
        result["error"] = error
    return result


def _extract_pdf_version(data: bytes) -> str:
    match = re.search(rb"%PDF-(\d+\.\d+)", data[:32])
    return match.group(1).decode("ascii") if match else "unknown"


def _extract_js_blocks(text: str) -> list[dict]:
    """Extract bounded JavaScript snippets from simple inline and hex forms."""
    blocks: list[dict] = []
    for match in re.finditer(r"/JS\s*\((.*?)\)", text, re.DOTALL | re.IGNORECASE):
        code = match.group(1)[:500]
        blocks.append(
            {"type": "inline", "preview": code, "length": len(match.group(1))}
        )
    for match in re.finditer(r"/JS\s*<([0-9A-Fa-f]+)>", text, re.IGNORECASE):
        try:
            decoded = bytes.fromhex(match.group(1)).decode("utf-8", errors="replace")
        except ValueError:
            continue
        blocks.append(
            {
                "type": "hex_encoded",
                "preview": decoded[:500],
                "length": len(decoded),
            }
        )
    return blocks[:20]


def _scan_pdf_surface(path: Path) -> dict:
    """Perform PDFiD-style keyword and lightweight JS scans inside the sandbox."""
    data = path.read_bytes()
    text = data.decode("latin-1", errors="replace")

    keywords: dict[str, int] = {}
    risk_counts = {"high": 0, "medium": 0, "low": 0}
    for keyword, risk in _PDF_KEYWORD_RISK.items():
        count = text.count(keyword)
        if count <= 0:
            continue
        keywords[keyword] = count
        risk_counts[risk] += count

    structure = {
        "pdf_version": _extract_pdf_version(data),
        "object_count": len(re.findall(rb"\d+\s+\d+\s+obj\b", data)),
        "stream_count": text.count("stream"),
        "endstream_count": text.count("endstream"),
        "xref_count": text.count("xref"),
        "trailer_count": text.count("trailer"),
        "startxref_count": text.count("startxref"),
        "page_count": len(re.findall(r"/Type\s*/Page\b(?!s)", text)),
        "encrypted": "/Encrypt" in text,
    }

    js_blocks = _extract_js_blocks(text)
    js_corpus = "\n".join(block["preview"] for block in js_blocks) or text[:20000]
    markers: dict[str, int] = {}
    for name, pattern in _JS_MARKER_PATTERNS.items():
        matches = re.findall(pattern, js_corpus, re.IGNORECASE)
        if matches:
            markers[name] = len(matches)

    uris = sorted(set(re.findall(r"https?://[^\s<>\"')\]]+", text)))[:50]
    submit_targets = sorted(
        set(re.findall(r"/SubmitForm\b[^()<>]*(https?://[^\s<>\"')\]]+)", text))
    )[:20]

    return {
        "keyword_summary": {
            "keywords": keywords,
            "risk_counts": risk_counts,
            "structure": structure,
            "has_jbig2decode": keywords.get("/JBIG2Decode", 0) > 0,
            "has_submit_form": keywords.get("/SubmitForm", 0) > 0,
            "has_object_stream": keywords.get("/ObjStm", 0) > 0,
            "has_open_action": keywords.get("/OpenAction", 0) > 0,
            "has_launch": keywords.get("/Launch", 0) > 0,
            "has_js": keywords.get("/JS", 0) > 0 or keywords.get("/JavaScript", 0) > 0,
            "has_embedded_file": keywords.get("/EmbeddedFile", 0) > 0,
        },
        "js_analysis": {
            "blocks": js_blocks,
            "markers": markers,
            "has_shellcode_markers": any(k in markers for k in _SHELLCODE_MARKERS),
            "has_obfuscation_markers": any(k in markers for k in _OBFUSCATION_MARKERS),
        },
        "uris": uris,
        "submit_targets": submit_targets,
    }


def _suggest_payload_format(name: str, data: bytes) -> str:
    """Infer an embedded payload type from magic bytes first, filename second."""
    if data.startswith(b"MZ"):
        return "pe"
    if data.startswith(b"\x7fELF"):
        return "elf"
    if data.startswith((b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa")):
        return "mach-o"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return "archive"
    stripped = data[:256].lstrip().lower()
    if stripped.startswith((b"#!", b"<script", b"function", b"var ", b"powershell")):
        return "script"

    suffix = Path(name).suffix.lower()
    if suffix in {".exe", ".dll", ".scr", ".sys", ".ocx"}:
        return "pe"
    if suffix in {
        ".js",
        ".jse",
        ".vbs",
        ".vbe",
        ".ps1",
        ".hta",
        ".wsf",
        ".bat",
        ".cmd",
    }:
        return "script"
    if suffix in {".zip", ".rar", ".7z", ".cab", ".iso"}:
        return "archive"
    if suffix in {".dylib", ".bundle", ".kext"}:
        return "mach-o"
    return "unknown"


def _materialize_payload(sample_path: Path, data: bytes, index: int) -> str | None:
    """Write embedded bytes beside the sample and return the sandbox path."""
    if not data:
        return None

    sha = hashlib.sha256(data).hexdigest()
    children_dir = sample_path.parent / "children"
    children_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = children_dir / f"pdf_embedded_{index:03d}_{sha[:16]}.bin"
    extracted_path.write_bytes(data)
    return extracted_path.as_posix()


def _run(sample_path: str) -> dict:
    path = Path(sample_path)
    if not path.exists():
        return _empty_result_with(error=f"sample not found: {sample_path}")

    try:
        scan = _scan_pdf_surface(path)
    except Exception as exc:  # noqa: BLE001
        scan = {}
        scan_error = f"pdf surface scan failed: {exc}"
    else:
        scan_error = None

    try:
        # peepdf is sandbox-only; import is intentional here (ADR-DOC-01).
        import peepdf  # type: ignore[import-untyped]  # noqa: F401
        from peepdf.PDFCore import PDFParser  # type: ignore[import-untyped]
    except ImportError as exc:
        error = f"peepdf not available: {exc}"
        if scan_error:
            error = f"{error}; {scan_error}"
        return _empty_result_with(scan, error)

    try:
        pdf_parser = PDFParser()
        ret, pdf = pdf_parser.parse(str(path), forceMode=True, manualAnalysis=False)
        if ret != 0 or pdf is None:
            return _empty_result_with(scan, "peepdf parse returned non-zero")
    except Exception as exc:  # noqa: BLE001
        return _empty_result_with(scan, f"peepdf parse exception: {exc}")

    object_tree: list[dict] = []
    triggers: list[dict] = []
    embedded_files: list[dict] = []
    action_chains: list[dict] = []
    xfa_present = False
    xfa_script_count = 0

    try:
        stats = pdf.getStats()

        # Object tree summary
        for obj_id_str, obj_info in (stats.get("Objects", {}) or {}).items():
            object_tree.append(
                {
                    "obj_id": int(obj_id_str)
                    if str(obj_id_str).isdigit()
                    else obj_id_str,
                    "obj_type": str(obj_info.get("type", "unknown")),
                    "contains_js": bool(obj_info.get("contains_js", False)),
                }
            )

        # Triggers
        for action_desc in stats.get("Actions", []) or []:
            triggers.append(
                {
                    "type": str(action_desc.get("type", "unknown")),
                    "action_type": str(action_desc.get("action", "")),
                    "js_preview": str(action_desc.get("js", ""))[:256],
                }
            )

        # Embedded files
        for index, emb in enumerate(stats.get("Embedded files", []) or [], start=1):
            data = emb.get("data", b"") or b""
            if isinstance(data, str):
                data = data.encode("latin-1", errors="replace")
            sha = hashlib.sha256(data).hexdigest() if data else ""
            name = str(emb.get("name", ""))
            extracted_to = _materialize_payload(path, data, index)
            materialized = extracted_to is not None
            item = {
                "name": name,
                "sha256": sha,
                "size_bytes": len(data),
                "suggested_format": _suggest_payload_format(name, data),
                "materialized": materialized,
            }
            if extracted_to:
                item["extracted_to"] = extracted_to
            embedded_files.append(item)

        # Action chains (trigger chains)
        for chain_info in stats.get("Action chains", []) or []:
            action_chains.append({"chain": list(chain_info)})

        # XFA forms
        xfa_info = stats.get("XFA", {}) or {}
        xfa_present = bool(xfa_info.get("present", False))
        xfa_script_count = int(xfa_info.get("script_count", 0))

    except Exception as exc:  # noqa: BLE001
        return {
            **_empty_result_with(scan),
            "object_tree": object_tree,
            "triggers": triggers,
            "embedded_files": embedded_files,
            "action_chains": action_chains,
            "xfa_form": {"present": xfa_present, "script_count": xfa_script_count},
            "error": f"stats extraction partial failure: {exc}",
        }

    return {
        **_empty_result_with(scan),
        "object_tree": object_tree,
        "triggers": triggers,
        "embedded_files": embedded_files,
        "action_chains": action_chains,
        "xfa_form": {"present": xfa_present, "script_count": xfa_script_count},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="peepdf PDF analysis worker")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({**_EMPTY_RESULT, "error": f"bad input: {exc}"}))
        sys.exit(1)

    result = _run(sample_path=payload.get("sample_path", ""))
    print(json.dumps(result))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
