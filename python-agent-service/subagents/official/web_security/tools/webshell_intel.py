"""Language-neutral webshell behavior, IOC, and ATT&CK extraction."""

from __future__ import annotations

import re

from .models import IOC, MitreTechnique

WebshellIntel = tuple[
    list[str],
    list[str],
    list[IOC],
    list[MitreTechnique],
    list[str],
]

_URL = re.compile(r"https?://[^\s'\"<>]{4,200}", re.I)
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

_PARAM_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\$_(GET|POST|REQUEST|COOKIE)\s*\[\s*"
            r"['\"]([^'\"]{1,80})['\"]\s*\]"
        ),
        "php",
    ),
    (
        re.compile(
            r"request\.getParameter\s*\(\s*['\"]([^'\"]{1,80})['\"]",
            re.I,
        ),
        "jsp",
    ),
    (
        re.compile(
            r"Request(?:\.QueryString|\.Form)?\s*\[\s*"
            r"['\"]([^'\"]{1,80})['\"]",
            re.I,
        ),
        "aspx",
    ),
    (
        re.compile(
            r"request\.(?:args|form|values|cookies)\.get\s*\(\s*"
            r"['\"]([^'\"]{1,80})['\"]",
            re.I,
        ),
        "python",
    ),
    (
        re.compile(
            r"URLSearchParams\s*\([^)]*\)\.get\s*\(\s*"
            r"['\"]([^'\"]{1,80})['\"]",
            re.I,
        ),
        "javascript",
    ),
)


def _add_mitre(
    mitre: dict[str, MitreTechnique],
    technique_id: str,
    name: str,
    confidence: float,
    evidence: str,
) -> None:
    current = mitre.get(technique_id)
    if current and current.confidence >= confidence:
        return
    mitre[technique_id] = MitreTechnique(
        technique_id=technique_id,
        name=name,
        confidence=confidence,
        evidence=evidence,
    )


def extract_webshell_intel(
    texts: list[str],
    language: str = "",
) -> WebshellIntel:
    """Extract deterministic behavior summaries."""
    joined = "\n".join(texts)
    lowered = joined.lower()
    behaviors: set[str] = set()
    capabilities: set[str] = set()
    iocs: list[IOC] = []
    mitre: dict[str, MitreTechnique] = {}
    actions: set[str] = set()

    server_lang = language in {"php", "jsp", "aspx", "python"}

    if re.search(
        r"\b(eval|assert|create_function|compile|__import__)\s*\(",
        lowered,
    ) or re.search(r"\.eval\s*\(", joined, re.I):
        behaviors.add("dynamic_code_execution")
        capabilities.add("code_execution")
        if server_lang:
            _add_mitre(
                mitre,
                "T1505.003",
                "Server Software Component: Web Shell",
                0.9,
                "Server-side dynamic code execution sink",
            )

    if re.search(
        r"\b(system|exec|shell_exec|passthru|popen|proc_open)\s*\(",
        lowered,
    ) or re.search(
        r"(subprocess\.(run|call|popen|check_output)"
        r"|os\.(system|popen))\s*\(",
        joined,
        re.I,
    ) or re.search(
        r"(Runtime\.getRuntime\s*\(\s*\)\s*\.exec|ProcessBuilder|"
        r"Process\.Start|System\.Diagnostics\.Process)",
        joined,
        re.I,
    ) or re.search(
        r"child_process\.(exec|spawn|execFile)\s*\(",
        joined,
        re.I,
    ):
        behaviors.add("os_command_execution")
        capabilities.add("command_execution")
        _add_mitre(
            mitre,
            "T1059",
            "Command and Scripting Interpreter",
            0.85,
            "OS command execution sink",
        )
        if server_lang:
            _add_mitre(
                mitre,
                "T1505.003",
                "Server Software Component: Web Shell",
                0.88,
                "Server-side command execution primitive",
            )

    if re.search(
        r"\b(file_put_contents|fwrite|move_uploaded_file|copy|unlink)\s*\(",
        lowered,
    ) or re.search(
        r"(Files\.write|FileOutputStream|System\.IO\.File\.Write|"
        r"open\s*\([^)]*['\"]w)",
        joined,
        re.I,
    ):
        behaviors.add("filesystem_modification")
        capabilities.add("file_write")
        _add_mitre(
            mitre,
            "T1105",
            "Ingress Tool Transfer",
            0.65,
            "Filesystem write or upload primitive",
        )

    if re.search(
        r"\.(innerHTML|outerHTML)\s*=|document\.write\s*\(",
        joined,
        re.I,
    ):
        behaviors.add("dom_xss_sink")
        capabilities.add("dom_script_injection")

    for regex, family in _PARAM_PATTERNS:
        for match in regex.findall(joined):
            if isinstance(match, tuple):
                if family == "php":
                    source = f"$_{match[0]}"
                    name = match[1]
                else:
                    source = f"{family}.request"
                    name = match[0]
            else:
                source = f"{family}.request"
                name = match
            item = IOC(type="parameter", name=name, source=source)
            if item not in iocs:
                iocs.append(item)

    for url in _URL.findall(joined):
        item = IOC(type="url", value=url, source="web_artifact")
        if item not in iocs:
            iocs.append(item)
    for ip in _IP.findall(joined):
        item = IOC(type="ip", value=ip, source="web_artifact")
        if item not in iocs:
            iocs.append(item)

    if server_lang and capabilities:
        actions.add("Remove the webshell and rotate exposed credentials.")
        actions.add(
            "Preserve the file, access logs, and decoded payload hashes."
        )
    if "command_execution" in capabilities:
        actions.add("Review process history and outbound connections.")

    return (
        sorted(behaviors),
        sorted(capabilities),
        iocs,
        list(mitre.values()),
        sorted(actions),
    )
