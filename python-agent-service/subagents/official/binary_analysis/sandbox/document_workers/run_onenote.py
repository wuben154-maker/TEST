"""run_onenote.py — OneNote P2 three-phase extraction worker (FR-03 AC-11 / A-03).

Invocation (by host via SandboxClient)::

    python run_onenote.py --input <json_path>

Input JSON::

    {
        "sample_path": "/workspace/<aid>/sample.one"
    }

Stdout JSON contract (parser available)::

    {
        "file_data_stores": [
            {
                "guid": "89CA5A93-DCAB-4FC9-82C5-EB85F4FCE2AE",
                "extension": ".exe",
                "size_bytes": 8192,
                "sha256": "<hex64>",
                "suggested_format": "pe",
                "extracted_to": "/workspace/<aid>/children/onenote_fds_001_<sha16>.bin",
                "materialized": true
            }
        ],
        "fallback_strings_ioc": []
    }

Degraded contract (parser unavailable — A-03 fallback)::

    {
        "degraded": "parser_unavailable",
        "file_data_stores": [
            {
                "guid": "89CA5A93-DCAB-4FC9-82C5-EB85F4FCE2AE",
                "offset": 1024,
                "materialized": false,
                "suggested_format": "unknown"
            }
        ],
        "fallback_strings_ioc": [
            "http://evil.example/payload"
        ]
    }

Three-phase strategy (FR-03 AC-11)
------------------------------------
Phase 1 — Byte-level string extraction (always runs):
    ``re.findall`` for URLs, IPs, registry paths, and other IOC patterns.

Phase 2 — IOC classification:
    Classify raw strings into URL / IP / domain / registry / base64-blob buckets.

Phase 3 — ``FileDataStoreObject`` GUID scan:
    Scan raw bytes for the known ``FileDataStoreObject`` class GUID and its
    neighbours to extract embedded file metadata.  When ``pyOneNote`` is
    available its higher-fidelity parser is used instead.

Security (NFR-04 / IR-DOC-01)
------------------------------
This worker performs byte-level and structural analysis only.  It never
executes embedded scripts or opens the OneNote application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Known FileDataStoreObject GUID (little-endian bytes in the .one stream).
# Reference: [MS-ONESTORE] §2.8.7
_FILE_DATA_STORE_GUID = bytes.fromhex(
    "935ACA89ABDC C94F82C5EB85F4FCE2AE".replace(" ", "")
)

# Simpler regex-based scan for the printable GUID form
_GUID_RE = re.compile(
    r"\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?",
    re.ASCII,
)

# IOC patterns for phase 1 / 2
_URL_RE = re.compile(rb"https?://[^\s\"'<>\x00-\x1f]{4,256}", re.IGNORECASE)
_IP_RE = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_REG_RE = re.compile(rb"HKEY_[A-Z_]+(?:\\[^\\\x00]+)+", re.IGNORECASE)


def _extract_iocs(data: bytes) -> list[str]:
    iocs: list[str] = []
    for m in _URL_RE.finditer(data):
        iocs.append(m.group().decode("latin-1", errors="replace"))
    for m in _IP_RE.finditer(data):
        iocs.append(m.group().decode("latin-1", errors="replace"))
    for m in _REG_RE.finditer(data):
        iocs.append(m.group().decode("latin-1", errors="replace"))
    return list(dict.fromkeys(iocs))  # dedup preserving order


def _scan_guids_bytes(data: bytes) -> list[dict]:
    """Byte-level GUID scan — fallback when pyOneNote is unavailable."""
    results: list[dict] = []
    for m in _GUID_RE.finditer(data.decode("latin-1", errors="replace")):
        guid_str = m.group().strip("{}")
        results.append(
            {
                "guid": guid_str.upper(),
                "offset": m.start(),
                "materialized": False,
                "suggested_format": "unknown",
            }
        )
    return results


def _suggest_payload_format(extension: str, data: bytes) -> str:
    """Infer an embedded payload type from magic bytes first, extension second."""
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

    suffix = extension.lower()
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
    """Write FileDataStore bytes beside the sample and return the sandbox path."""
    if not data:
        return None

    sha = hashlib.sha256(data).hexdigest()
    children_dir = sample_path.parent / "children"
    children_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = children_dir / f"onenote_fds_{index:03d}_{sha[:16]}.bin"
    extracted_path.write_bytes(data)
    return extracted_path.as_posix()


def _run_with_pyonenote(sample_path: str) -> dict | None:
    """Attempt high-fidelity extraction via pyOneNote; return None on ImportError."""
    try:
        # pyOneNote is sandbox-only; import is intentional here (ADR-DOC-01).
        from pyOneNote.OneDocument import OneDocment  # type: ignore[import-untyped]
    except ImportError:
        return None

    path = Path(sample_path)
    file_data_stores: list[dict] = []

    try:
        doc = OneDocment(str(path))
        for index, fds in enumerate(doc.get_file_data_stores(), start=1):
            raw = bytes(fds.get_data() or b"")
            sha = hashlib.sha256(raw).hexdigest() if raw else ""
            ext = str(getattr(fds, "extension", "") or "")
            guid = str(getattr(fds, "guid", "") or "")
            extracted_to = _materialize_payload(path, raw, index)
            materialized = extracted_to is not None
            item = {
                "guid": guid,
                "extension": ext,
                "size_bytes": len(raw),
                "sha256": sha,
                "suggested_format": _suggest_payload_format(ext, raw),
                "materialized": materialized,
            }
            if extracted_to:
                item["extracted_to"] = extracted_to
            file_data_stores.append(item)
    except Exception as exc:  # noqa: BLE001
        return {
            "file_data_stores": file_data_stores,
            "fallback_strings_ioc": [],
            "error": f"pyOneNote parse error: {exc}",
        }

    return {
        "file_data_stores": file_data_stores,
        "fallback_strings_ioc": [],
    }


def _run(sample_path: str) -> dict:
    path = Path(sample_path)
    if not path.exists():
        return {
            "degraded": "file_not_found",
            "file_data_stores": [],
            "fallback_strings_ioc": [],
            "error": f"sample not found: {sample_path}",
        }

    # Phase 1/2: byte-level IOC extraction (always runs regardless of pyOneNote)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {
            "degraded": "read_error",
            "file_data_stores": [],
            "fallback_strings_ioc": [],
            "error": str(exc),
        }

    iocs = _extract_iocs(data)

    # Phase 3: try pyOneNote first (high-fidelity)
    result = _run_with_pyonenote(sample_path)
    if result is not None:
        result["fallback_strings_ioc"] = iocs
        return result

    # A-03 degraded path: byte-level GUID scan
    guids = _scan_guids_bytes(data)
    return {
        "degraded": "parser_unavailable",
        "file_data_stores": guids,
        "fallback_strings_ioc": iocs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OneNote extraction worker")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "degraded": "bad_input",
                    "file_data_stores": [],
                    "fallback_strings_ioc": [],
                    "error": f"bad input: {exc}",
                }
            )
        )
        sys.exit(1)

    result = _run(sample_path=payload.get("sample_path", ""))
    print(json.dumps(result))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
