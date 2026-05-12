"""Phase 3 tools: URL analysis, prompt injection, social engineering, quishing.

Provides both *individual* tools (backward-compatible) and two *merged* tools
that reduce the number of tool calls the LLM agent needs to make:

- `analyze_all_urls`: extract + per-URL risk + href mismatch in one call.
- `scan_body_threats`: prompt injection + social engineering in one call.

All analysis logic is self-contained — no external PhishGuard dependency.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Annotated, Any
from urllib.parse import unquote, urlparse

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from ._helpers import (
    BRAND_DOMAINS,
    SUSPICIOUS_TLDS,
    URL_SHORTENERS,
    _normalize_path,
    logger,
)
from .policy import domain_from_url, normalize_domain, normalize_url  # noqa: PLC0415

_URL_REGEX = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)
_URL_TRAILING = re.compile(r'[.,;:!?\'")\]]+$')


def _extract_urls_regex(text: str) -> list[str]:
    """Extract unique URLs from text using regex."""
    urls = _URL_REGEX.findall(text)
    cleaned: list[str] = []
    for url in urls:
        url = _URL_TRAILING.sub("", url)
        if url:
            cleaned.append(url)
    return list(set(cleaned))


def _get_domain(url: str) -> str:
    """Extract domain from URL, lowercase."""
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def _check_href_vs_display(html: str) -> list[dict[str, Any]]:
    """Compare ``<a href>`` with display text; return mismatches."""
    out: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>([^<]*)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(html):
        href = (m.group(1) or "").strip()
        display = (m.group(2) or "").strip()
        if not href:
            continue
        display_clean = re.sub(r"\s+", " ", display).strip()
        try:
            href_domain = _get_domain(href)
            if display_clean.startswith("http"):
                display_domain = _get_domain(display_clean)
                if display_domain and display_domain != href_domain:
                    out.append(
                        {
                            "href": href,
                            "display_text": display_clean[:200],
                            "mismatch": True,
                        }
                    )
            elif display_clean and href_domain and " " not in display_clean:
                if "." in display_clean and display_clean.lower() != href_domain:
                    out.append(
                        {
                            "href": href,
                            "display_text": display_clean[:200],
                            "mismatch": True,
                        }
                    )
        except Exception:
            pass
    return out


def _idn_homograph_check(domain: str) -> dict[str, Any]:
    """Check for IDN / homograph (e.g. paypal.com with Cyrillic ``a``)."""
    if not domain:
        return {"is_idn": False, "possibly_homograph": False, "ascii_form": ""}
    try:
        ascii_form = unicodedata.normalize("NFKC", domain)
        has_non_ascii = any(ord(c) > 127 for c in domain)
        changed = ascii_form != domain
        return {
            "is_idn": has_non_ascii,
            "possibly_homograph": has_non_ascii or changed,
            "ascii_form": ascii_form,
        }
    except Exception:
        return {"is_idn": False, "possibly_homograph": False, "ascii_form": domain}


def _url_sanitize_technical_proofs(
    html: str | None,
    urls: list[str],
    *,
    expand_shortlinks: bool = True,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """Produce technical_proofs entries for URL_MISMATCH and IDN."""
    proofs: list[dict[str, Any]] = []
    if html:
        for item in _check_href_vs_display(html):
            if item.get("mismatch"):
                proofs.append(
                    {
                        "component": "URL_MISMATCH",
                        "status": "ANOMALY",
                        "detail": (
                            f"Display text '{item.get('display_text', '')[:80]}...' "
                            f"does not match href '{item.get('href', '')[:80]}'."
                        ),
                    }
                )
    for url in urls:
        d = _get_domain(url)
        if not d:
            continue
        info = _idn_homograph_check(d)
        if info.get("possibly_homograph"):
            proofs.append(
                {
                    "component": "IDN",
                    "status": "ANOMALY",
                    "detail": (
                        f"IDN/homograph domain: {d} (normalized: {info.get('ascii_form', '')})"
                    ),
                }
            )
    return proofs


try:
    from pyzbar import pyzbar as _pyzbar_mod  # type: ignore[import-not-found] # noqa: PLC0415
    from PIL import Image as _pil_image  # type: ignore[import-not-found] # noqa: PLC0415

    _HAS_PYZBAR = True
except Exception:
    _pyzbar_mod = None  # type: ignore[assignment]
    _pil_image = None  # type: ignore[assignment]
    _HAS_PYZBAR = False


def _scan_images_for_qr(images: list[bytes]) -> list[dict[str, Any]]:
    """Scan each image for QR codes; return list of ``{url, image_index, type}``."""
    if not _HAS_PYZBAR:
        return []
    assert _pil_image is not None
    assert _pyzbar_mod is not None
    import io as _io  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    for i, blob in enumerate(images):
        try:
            img = _pil_image.open(_io.BytesIO(blob)).convert("RGB")
            decoded = _pyzbar_mod.decode(img)
            for obj in decoded:
                if obj.type == "QRCODE" and obj.data:
                    try:
                        url = obj.data.decode("utf-8", errors="replace").strip()
                        if url.startswith(("http://", "https://")):
                            out.append({"url": url, "image_index": i, "type": "QRCODE"})
                    except Exception:
                        pass
        except Exception:
            continue
    return out


_CONFUSABLE_CHARS: dict[str, str] = {
    "\u0430": "a",
    "\u0435": "e",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0443": "y",
    "\u0445": "x",
    "\u0456": "i",
}


def _extract_urls_from_html(html: str) -> list[str]:
    """Extract URLs from HTML ``href``, ``src``, and ``action`` attributes."""
    found: list[str] = []

    class _LinkParser(HTMLParser):
        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            for attr_name, attr_val in attrs:
                if attr_name in ("href", "src", "action") and attr_val:
                    val = attr_val.strip()
                    if val.startswith(("http://", "https://", "data:", "mailto:", "//")):
                        found.append(val)

    try:
        _LinkParser().feed(html)
    except Exception:
        pass
    return found


@tool
def extract_urls_tool(
    text: str,
    max_urls: Annotated[int, "Maximum number of URLs to return."] = 30,
) -> list[str]:
    """Extract unique URLs from text (plain text or HTML)."""
    urls: set[str] = set()
    urls.update(_extract_urls_regex(text))
    urls.update(_extract_urls_from_html(text))
    return sorted(urls)[:max_urls]


@tool
def analyze_url_tool(url: str) -> dict[str, Any]:
    """Analyze a URL for suspicious characteristics."""
    result: dict[str, Any] = {
        "url": url,
        "parsed": None,
        "suspicious_indicators": [],
        "indicators": [],
        "risk_level": "low",
    }
    _enhance_url_analysis(url, result)
    return result


def _enhance_url_analysis(url: str, result: dict[str, Any]) -> None:
    """Run all URL risk checks: homograph, typosquat, shortener, TLD, IP, etc."""
    indicators = result.setdefault("suspicious_indicators", [])
    if "indicators" not in result or result.get("indicators") is result["indicators"]:
        result["indicators"] = indicators

    if url.lower().startswith("data:"):
        indicators.append("data_uri_detected")
        result["risk_level"] = "high"
        return

    if url.lower().startswith("mailto:"):
        indicators.append("mailto_link")
        return

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        domain: str = (
            (hostname if isinstance(hostname, str) else hostname.decode())
            if hostname
            else ""
        ).lower()
    except (ValueError, AttributeError, UnicodeDecodeError):
        return

    result["parsed"] = {
        "scheme": parsed.scheme,
        "domain": parsed.netloc,
        "path": parsed.path,
        "query": parsed.query,
    }

    if not domain:
        return

    base_domain = ".".join(domain.split(".")[-2:]) if "." in domain else domain
    if base_domain in URL_SHORTENERS or domain in URL_SHORTENERS:
        indicators.append("url_shortener")
        if result.get("risk_level") != "high":
            result["risk_level"] = "medium"

    for tld in SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            indicators.append(f"suspicious_tld_{tld}")
            if result.get("risk_level") != "high":
                result["risk_level"] = "medium"
            break

    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", domain):
        indicators.append("ip_address_instead_of_domain")
        if result.get("risk_level") != "high":
            result["risk_level"] = "medium"

    if _has_mixed_scripts(domain):
        indicators.append("mixed_unicode_scripts_in_domain")
        result["risk_level"] = "high"

    for confusable in _CONFUSABLE_CHARS:
        if confusable in domain:
            indicators.append(f"confusable_char_{confusable!r}_in_domain")
            result["risk_level"] = "high"
            break

    brand = _check_typosquat(domain)
    if brand:
        indicators.append(f"possible_typosquat_of_{brand}")
        if result.get("risk_level") != "high":
            result["risk_level"] = "medium"

    path = parsed.path or ""
    if "%" in path and unquote(path) != path:
        indicators.append("url_encoding_in_path")

    url_lower = url.lower()
    for kw in (
        "login",
        "signin",
        "verify",
        "secure",
        "account",
        "update",
        "confirm",
        "banking",
        "password",
        "credential",
    ):
        if kw in url_lower:
            indicators.append(f"suspicious_keyword_{kw}")
            break

    if len(indicators) >= 3 and result.get("risk_level") != "high":
        result["risk_level"] = "high"


def _has_mixed_scripts(domain: str) -> bool:
    """Detect mixed Unicode scripts in a domain."""
    scripts: set[str] = set()
    for ch in domain:
        if ch in (".", "-"):
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            name = unicodedata.name(ch, "")
            if "LATIN" in name:
                scripts.add("LATIN")
            elif "CYRILLIC" in name:
                scripts.add("CYRILLIC")
            elif "CJK" in name:
                scripts.add("CJK")
            else:
                scripts.add("OTHER")
    return len(scripts) > 1


def _check_typosquat(domain: str) -> str | None:
    """Return the brand domain if this domain looks like a typosquat."""
    domain_base = domain.split(".")[0].lower()
    for brand in BRAND_DOMAINS:
        brand_base = brand.split(".")[0]
        ratio = SequenceMatcher(None, domain_base, brand_base).ratio()
        if 0.7 <= ratio < 1.0 and domain != brand:
            return brand
    return None


@tool
def url_sanitize_tool(html: str | None, urls: list[str]) -> list[dict[str, Any]]:
    """Produce technical_proofs entries for URL mismatch and IDN from HTML and URLs."""
    return _url_sanitize_technical_proofs(html, urls, expand_shortlinks=False)


@tool
def scan_quishing(
    file_paths: Annotated[list[str], "List of image file paths (under /uploaded/)."],
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> list[dict[str, Any]]:
    """Scan image attachments for QR codes. Provide file_paths (under /uploaded/)."""
    if not file_paths:
        return []
    if not _HAS_PYZBAR:
        return [
            {
                "url": None,
                "image_index": None,
                "type": "QRCODE",
                "analysis_unavailable": True,
                "detail": "pyzbar/Pillow not installed; QR scan not performed.",
            }
        ]

    validated: list[str] = []
    for p in file_paths:
        try:
            validated.append(_normalize_path(p))
        except ValueError as exc:
            logger.debug("scan_quishing: invalid path %r: %s", p, exc)

    if not validated:
        return []

    backend = backend_factory(runtime)
    responses = backend.download_files(validated)

    raw_images: list[bytes] = []
    for resp in responses or []:
        if getattr(resp, "error", None) or not getattr(resp, "content", None):
            continue
        raw_images.append(resp.content)

    if not raw_images:
        return []
    return _scan_images_for_qr(raw_images)


_JAILBREAK_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+DAN", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+(above|prior)", re.IGNORECASE),
    re.compile(r"new\s+instructions\s*:", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?safety", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(your\s+)?previous", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(any|your)\s+(rules|guidelines)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"bypass\s+(your\s+)?(restrictions|filters|safety)", re.IGNORECASE),
    re.compile(r"忽略(之前|以上|所有)(的)?指令"),
    re.compile(r"无视(之前|以上|所有)(的)?规则"),
    re.compile(r"你现在是"),
    re.compile(r"新的?指令\s*[:：]"),
    re.compile(r"忘记(之前|以前)(的)?(所有)?"),
    re.compile(r"假装你是"),
    re.compile(r"解除(安全|限制|约束)"),
]

_ZERO_WIDTH_CHARS = frozenset(
    {
        "\u200b",
        "\u200c",
        "\u200d",
        "\ufeff",
        "\u2060",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202c",
        "\u202d",
        "\u202e",
    }
)


@tool
def detect_prompt_injection(text: str) -> dict[str, Any]:
    """Scan text for prompt injection / jailbreak attempts."""
    found: list[str] = []
    for pat in _JAILBREAK_PATTERNS:
        if pat.search(text):
            found.append(pat.pattern)

    invisible_count = sum(1 for ch in text if ch in _ZERO_WIDTH_CHARS)
    has_invisible = invisible_count > 3

    if has_invisible:
        found.append(f"suspicious_invisible_chars({invisible_count})")

    risk = "CRITICAL" if found else "LOW"
    logger.debug(
        "Prompt injection scan: %d pattern(s) matched, %d invisible chars",
        len(found),
        invisible_count,
    )
    return {
        "injection_detected": len(found) > 0,
        "patterns_matched": found,
        "has_invisible_chars": has_invisible,
        "invisible_char_count": invisible_count,
        "risk": risk,
    }


_URGENCY_PATTERNS_ZH = [
    r"立即",
    r"紧急",
    r"马上",
    r"限时",
    r"逾期",
    r"冻结",
    r"验证.*身份",
    r"确认.*账[户号]",
    r"重置.*密码",
    r"24小时",
]
_URGENCY_PATTERNS_EN = [
    r"immediately",
    r"urgent",
    r"verify your (?:account|identity)",
    r"suspend",
    r"within \d+ hours?",
    r"click (?:here|below) to",
    r"confirm your (?:payment|order)",
    r"unauthorized (?:access|activity)",
    r"your account (?:has been|will be) (?:locked|suspended|closed)",
    r"act now",
    r"limited time",
]

_STRONG_SE_PATTERNS_ZH: list[tuple[str, str]] = [
    (r"(公安|派出所|检察院|法院|税务局|海关|人社|社保|医保|工信部|银监|证监)", "authority_impersonation_zh"),
    (r"(传票|拘留|逮捕|立案|刑事|行政处罚|罚款|追责|起诉|诉讼|法律责任)", "legal_threat_zh"),
    (r"(最后通牒|最后期限|限期|截止(日期|时间)?|逾期(将)?(冻结|处理|追责))", "deadline_threat_zh"),
    (r"(账户|账号).{0,12}(冻结|封禁|停用|注销|暂停)", "account_freeze_zh"),
    (r"(立即|马上|立刻).{0,20}(处理|缴费|确认|验证|申诉|更新)", "urgent_action_zh"),
]
_STRONG_SE_PATTERNS_EN: list[tuple[str, str]] = [
    (r"\b(irs|tax|customs|police|court|government|social security|hmrc)\b", "authority_impersonation_en"),
    (r"\b(summons|arrest|prosecution|legal action|lawsuit|penalty|fine)\b", "legal_threat_en"),
    (r"\b(final notice|last chance|deadline|due (?:today|now)|within \d+ (?:hours?|days?))\b", "deadline_threat_en"),
    (r"\b(account|payment).{0,20}\b(suspended|frozen|locked|disabled|terminated)\b", "account_freeze_en"),
]


def _extract_evidence_snippets(
    text: str, pattern: str, *, max_snippets: int = 3, window: int = 60
) -> list[str]:
    snippets: list[str] = []
    try:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, m.start() - window)
            end = min(len(text), m.end() + window)
            snippet = text[start:end].strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet[:250])
            if len(snippets) >= max_snippets:
                break
    except re.error:
        return []
    return snippets


def score_strong_social_engineering(text: str) -> dict[str, Any]:
    """Score text for strong social engineering signals (authority/legal/deadlines)."""
    if not text:
        return {"risk": "LOW", "score": 0, "matched_patterns": [], "evidence": []}

    matched: list[str] = []
    evidence: list[str] = []
    for pat, label in _STRONG_SE_PATTERNS_ZH + _STRONG_SE_PATTERNS_EN:
        if re.search(pat, text, re.IGNORECASE):
            matched.append(label)
            evidence.extend(_extract_evidence_snippets(text, pat))

    score = min(len(matched) * 25, 100)
    risk = "HIGH" if score >= 50 else ("MEDIUM" if score >= 25 else "LOW")
    return {
        "risk": risk,
        "score": score,
        "matched_patterns": matched,
        "evidence": evidence[:5],
    }


@tool
def score_social_engineering(body_text: str) -> dict[str, Any]:
    """Score email body for social engineering / urgency patterns."""
    matches: list[str] = []
    text_lower = body_text.lower()
    for pattern in _URGENCY_PATTERNS_ZH + _URGENCY_PATTERNS_EN:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matches.append(pattern)
    score = min(len(matches) * 15, 100)
    risk = "HIGH" if score >= 60 else ("MEDIUM" if score >= 30 else "LOW")
    return {
        "risk": risk,
        "score": score,
        "matched_patterns": matches,
        "detail": f"Social engineering score: {score}/100 ({len(matches)} pattern(s) matched).",
    }


@tool
def analyze_all_urls(
    body_text: Annotated[str | None, "Plain text email body."] = None,
    body_html: Annotated[str | None, "HTML email body."] = None,
    max_urls: Annotated[int, "Maximum URLs to analyze."] = 30,
) -> dict[str, Any]:
    """Extract URLs from email body, analyze each for risk, and detect href mismatches."""
    urls: set[str] = set()
    for source in (body_text, body_html):
        if not source:
            continue
        urls.update(_extract_urls_regex(source))
        urls.update(_extract_urls_from_html(source))

    url_list = list(urls)[:max_urls]

    analyses: list[dict[str, Any]] = []
    for url in url_list:
        result: dict[str, Any] = {
            "url": url,
            "parsed": None,
            "suspicious_indicators": [],
            "indicators": [],
            "risk_level": "low",
        }
        _enhance_url_analysis(url, result)
        analyses.append(result)

    sanitize_proofs: list[dict[str, Any]] = []
    if body_html:
        sanitize_proofs = _url_sanitize_technical_proofs(
            body_html, url_list, expand_shortlinks=False
        )

    high = sum(1 for a in analyses if a.get("risk_level") == "high")
    medium = sum(1 for a in analyses if a.get("risk_level") == "medium")

    logger.debug(
        "analyze_all_urls: %d URLs, %d high, %d medium", len(url_list), high, medium
    )
    evidence: list[dict[str, Any]] = []
    for a in analyses:
        u = str(a.get("url") or "")
        risk = str(a.get("risk_level") or "low")
        dom = domain_from_url(u)
        indicators = a.get("indicators") or []
        if risk in {"high", "medium"}:
            evidence.append(
                {
                    "signal": f"url_risk_{risk}",
                    "severity": "HIGH" if risk == "high" else "MEDIUM",
                    "confidence": "high",
                    "artifact": {
                        "type": "url",
                        "value": normalize_url(u),
                        "context": {"domain": dom},
                    },
                    "source": "analyze_all_urls",
                    "detail": f"URL classified as {risk} risk by static checks.",
                    "details": {"indicators": indicators[:20]},
                }
            )
        for ind in indicators[:20]:
            if isinstance(ind, str) and ind:
                evidence.append(
                    {
                        "signal": f"url_indicator_{ind}",
                        "severity": "LOW",
                        "confidence": "high",
                        "artifact": {
                            "type": "url",
                            "value": normalize_url(u),
                            "context": {"domain": dom},
                        },
                        "source": "analyze_all_urls",
                        "detail": f"URL indicator: {ind}",
                    }
                )

    for p in sanitize_proofs or []:
        comp = p.get("component")
        detail = p.get("detail")
        if not isinstance(detail, str) or not detail:
            continue
        if comp == "URL_MISMATCH":
            evidence.append(
                {
                    "signal": "url_href_display_mismatch",
                    "severity": "MEDIUM",
                    "confidence": "high",
                    "artifact": None,
                    "source": "analyze_all_urls",
                    "detail": detail,
                }
            )
        elif comp == "IDN":
            evidence.append(
                {
                    "signal": "url_idn_homograph",
                    "severity": "HIGH",
                    "confidence": "high",
                    "artifact": None,
                    "source": "analyze_all_urls",
                    "detail": detail,
                }
            )

    return {
        "urls_found": len(url_list),
        "url_analyses": analyses,
        "sanitize_proofs": sanitize_proofs,
        "high_risk_count": high,
        "medium_risk_count": medium,
        "evidence": evidence,
    }


@tool
def scan_body_threats(
    body_text: Annotated[str, "Email body text to scan."],
) -> dict[str, Any]:
    """Scan email body for prompt injection and social engineering indicators."""
    pi_found: list[str] = []
    for pat in _JAILBREAK_PATTERNS:
        if pat.search(body_text):
            pi_found.append(pat.pattern)

    invisible_count = sum(1 for ch in body_text if ch in _ZERO_WIDTH_CHARS)
    has_invisible = invisible_count > 3
    if has_invisible:
        pi_found.append(f"suspicious_invisible_chars({invisible_count})")

    pi_detected = len(pi_found) > 0
    pi_risk = "CRITICAL" if pi_detected else "LOW"

    se_matches: list[str] = []
    text_lower = body_text.lower()
    for pattern in _URGENCY_PATTERNS_ZH + _URGENCY_PATTERNS_EN:
        if re.search(pattern, text_lower, re.IGNORECASE):
            se_matches.append(pattern)
    se_score = min(len(se_matches) * 15, 100)
    se_risk = "HIGH" if se_score >= 60 else ("MEDIUM" if se_score >= 30 else "LOW")

    logger.debug(
        "scan_body_threats: pi=%s (%d patterns), se_score=%d (%d patterns)",
        pi_detected,
        len(pi_found),
        se_score,
        len(se_matches),
    )
    return {
        "prompt_injection": {
            "detected": pi_detected,
            "patterns": pi_found,
            "has_invisible_chars": has_invisible,
            "invisible_char_count": invisible_count,
            "risk": pi_risk,
        },
        "social_engineering": {
            "risk": se_risk,
            "score": se_score,
            "matched_patterns": se_matches,
        },
        "evidence": [
            *(
                [
                    {
                        "signal": "body_prompt_injection_detected",
                        "severity": "CRITICAL",
                        "confidence": "high",
                        "artifact": None,
                        "source": "scan_body_threats",
                        "detail": f"Prompt injection patterns matched: {len(pi_found)}",
                        "details": {
                            "patterns": pi_found[:10],
                            "invisible_char_count": invisible_count,
                        },
                    }
                ]
                if pi_detected
                else []
            ),
            *(
                [
                    {
                        "signal": "body_social_engineering_detected",
                        "severity": (
                            "HIGH"
                            if se_risk == "HIGH"
                            else ("MEDIUM" if se_risk == "MEDIUM" else "LOW")
                        ),
                        "confidence": "high",
                        "artifact": None,
                        "source": "scan_body_threats",
                        "detail": f"Social engineering score={se_score} risk={se_risk}.",
                        "details": {"matched_patterns": se_matches[:10]},
                    }
                ]
                if se_score > 0
                else []
            ),
        ],
    }

