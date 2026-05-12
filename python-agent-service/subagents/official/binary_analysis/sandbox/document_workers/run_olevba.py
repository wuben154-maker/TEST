"""run_olevba.py — VBA / XL4 macro extraction worker (FR-03 AC-1/2/3).

Invocation (by host via SandboxClient)::

    python run_olevba.py --input <json_path>

where ``<json_path>`` is a file containing::

    {
        "sample_path": "/workspace/<aid>/sample.xlsm",
        "options": {
            "reveal_suspicious": true
        }
    }

Stdout JSON contract::

    {
        "vba_modules": [
            {
                "name": "Module1",
                "source_hash": "sha256:<hex64>",
                "source_preview": "<first 512 chars>",
                "code_page": "utf-8"
            }
        ],
        "xl4_macros": [
            {
                "cell": "HIDDEN!A1",
                "formula": "=EXEC(..."
            }
        ],
        "triggers": [
            {
                "type": "AutoOpen",
                "location": "VBA.ThisDocument"
            }
        ],
        "macro_actions": [
            {
                "action": "Shell",
                "args_literal": ["Suspicious keyword: Shell"],
                "source": "olevba_static"
            }
        ],
        "static_iocs": [
            {
                "type": "url",
                "value": "hxxp://example[.]invalid/payload",
                "source": "olevba_deobfuscated",
                "module": "Module1"
            }
        ]
    }

On error the JSON is ``{"error": "<message>", "vba_modules": [], "xl4_macros": [],
"triggers": [], "macro_actions": [], "static_iocs": []}``.

Security (NFR-04 / IR-DOC-01)
------------------------------
``oletools.olevba`` performs *static* VBA extraction — it never calls the
Windows Script Host or any Office COM interface.  This worker is intentionally
the only location that imports ``oletools``; do **not** import it in host code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_MAX_PREVIEW_CHARS = 512
_MAX_IOCS_PER_MODULE = 20
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_PS_CRADLE_RE = re.compile(
    r"(?i)powershell[^\n]*-(?:enc|e|nop|noprofile|w\s*hidden|ep\s*bypass)"
)
_LOLBIN_RE = re.compile(
    r"(?i)\b(?:powershell|pwsh|cmd(?:\.exe)?|mshta|certutil|regsvr32|"
    r"rundll32|wscript|cscript|bitsadmin|msiexec)\b"
)
_NETWORK_RE = re.compile(
    r"(?i)\b(?:xmlhttp|winhttprequest|urldownloadtofile|webclient|"
    r"internetopen|downloadstring|openurl)\b|https?://"
)
_FILE_WRITE_RE = re.compile(
    r"(?i)\b(?:adodb\.stream|savetofile|writeallbytes|writefile|createtextfile)\b"
)
_COMMAND_RE = re.compile(r"(?i)\b(?:shell|run|exec|createprocess)\b")


def _hash_source(src: str) -> str:
    return "sha256:" + hashlib.sha256(src.encode()).hexdigest()


def _empty_result(error: str | None = None) -> dict:
    result: dict = {
        "vba_modules": [],
        "xl4_macros": [],
        "triggers": [],
        "macro_actions": [],
        "static_iocs": [],
    }
    if error is not None:
        result["error"] = error
    return result


def _resolve_chr_calls(code: str) -> str:
    def resolve(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1)))
        except (OverflowError, ValueError):
            return match.group(0)

    code = re.sub(r"Chr\$?\((\d+)\)", resolve, code, flags=re.IGNORECASE)
    return re.sub(r"ChrW\$?\((\d+)\)", resolve, code, flags=re.IGNORECASE)


def _deobfuscate_vba_preview(code: str) -> str:
    """Apply safe, local string-only deobfuscation and return a bounded preview."""
    out = _resolve_chr_calls(code)
    out = re.sub(r'"\s*&\s*"', "", out)
    out = re.sub(
        r'StrReverse\("([^"]+)"\)',
        lambda m: '"' + m.group(1)[::-1] + '"',
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r'Replace\("([^"]+)",\s*"([^"]+)",\s*"([^"]*)"\)',
        lambda m: '"' + m.group(1).replace(m.group(2), m.group(3)) + '"',
        out,
        flags=re.IGNORECASE,
    )
    return out[:_MAX_PREVIEW_CHARS]


def _extract_urls(code: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_RE.finditer(code):
        val = match.group(0)
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
        if len(out) >= _MAX_IOCS_PER_MODULE:
            break
    return out


def _static_macro_actions(module_name: str, code: str) -> list[dict]:
    actions: list[dict] = []
    checks: tuple[tuple[re.Pattern[str], str], ...] = (
        (_PS_CRADLE_RE, "powershell_cradle"),
        (_LOLBIN_RE, "lolbin"),
        (_NETWORK_RE, "network_request"),
        (_FILE_WRITE_RE, "file_write"),
        (_COMMAND_RE, "command_invocation"),
    )
    for pattern, action in checks:
        match = pattern.search(code)
        if match is None:
            continue
        actions.append(
            {
                "action": action,
                "args_literal": [match.group(0)[:160]],
                "source": "olevba_static",
                "module": module_name,
            }
        )
    return actions


def _run(sample_path: str, options: dict) -> dict:  # noqa: ARG001
    try:
        from oletools.olevba import VBA_Parser  # type: ignore[import-untyped]
    except ImportError as exc:
        return _empty_result(f"oletools not available: {exc}")

    path = Path(sample_path)
    if not path.exists():
        return _empty_result(f"sample not found: {sample_path}")

    try:
        vba_parser = VBA_Parser(str(path))
    except Exception as exc:  # noqa: BLE001
        return _empty_result(f"VBA_Parser init failed: {exc}")

    vba_modules: list[dict] = []
    xl4_macros: list[dict] = []
    triggers: list[dict] = []
    macro_actions: list[dict] = []
    static_iocs: list[dict] = []

    try:
        if vba_parser.detect_vba_macros():
            for _, _, vba_filename, vba_code in vba_parser.extract_macros():
                src = vba_code or ""
                deobfuscated_preview = _deobfuscate_vba_preview(src)
                urls = _extract_urls(src + "\n" + deobfuscated_preview)
                vba_modules.append(
                    {
                        "name": vba_filename,
                        "source_hash": _hash_source(src),
                        "source_preview": src[:_MAX_PREVIEW_CHARS],
                        "deobfuscated_preview": deobfuscated_preview,
                        "deobfuscated_changed": deobfuscated_preview
                        != src[:_MAX_PREVIEW_CHARS],
                        "code_page": "utf-8",
                    }
                )
                macro_actions.extend(_static_macro_actions(vba_filename, src))
                static_iocs.extend(
                    {
                        "type": "url",
                        "value": url,
                        "source": "olevba_deobfuscated",
                        "module": vba_filename,
                    }
                    for url in urls
                )

        # XL4 / Excel 4.0 macros (oletools ≥ 0.60)
        if hasattr(vba_parser, "detect_xl4_macros") and vba_parser.detect_xl4_macros():
            for xl4 in vba_parser.extract_xl4_macros():
                xl4_macros.append({"cell": str(xl4[0]), "formula": str(xl4[1])})

        # Auto-open / trigger keywords from analysis
        if hasattr(vba_parser, "analyze_macros"):
            for kw_type, keyword, description in vba_parser.analyze_macros():
                if kw_type == "AutoExec":
                    triggers.append({"type": keyword, "location": description})
                elif kw_type == "Suspicious":
                    macro_actions.append(
                        {
                            "action": keyword,
                            "args_literal": [description],
                            "source": "olevba_analyze_macros",
                        }
                    )
                elif kw_type == "IOC":
                    static_iocs.append(
                        {
                            "type": "olevba_ioc",
                            "value": keyword,
                            "source": "olevba_analyze_macros",
                        }
                    )

    except Exception as exc:  # noqa: BLE001
        result = _empty_result(f"macro extraction failed: {exc}")
        result.update(
            {
                "vba_modules": vba_modules,
                "xl4_macros": xl4_macros,
                "triggers": triggers,
                "macro_actions": macro_actions,
                "static_iocs": static_iocs,
            }
        )
        return result
    finally:
        try:
            vba_parser.close()
        except Exception:  # noqa: BLE001
            pass

    return {
        "vba_modules": vba_modules,
        "xl4_macros": xl4_macros,
        "triggers": triggers,
        "macro_actions": macro_actions,
        "static_iocs": static_iocs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="olevba extraction worker")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps(_empty_result(f"bad input: {exc}")))
        sys.exit(1)

    result = _run(
        sample_path=payload.get("sample_path", ""),
        options=payload.get("options", {}),
    )
    print(json.dumps(result))
    if "error" in result and not result.get("vba_modules"):
        sys.exit(1)


if __name__ == "__main__":
    main()
