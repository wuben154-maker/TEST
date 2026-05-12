"""Merged image phishing analysis: OCR + strong social engineering + QR escalation.

This tool makes the "quishing escalation" rule deterministic in code:
- If an image has no meaningful OCR text but contains a QR code URL, and the URL
  is a shortlink or otherwise suspicious, the result is escalated to high risk.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool


def _meaningful_text(text: str) -> bool:
    return len("".join(text.split())) >= 20


def _get_tld(domain: str) -> str:
    parts = domain.rsplit(".", 1)
    if len(parts) != 2 or not parts[1]:
        return ""
    return f".{parts[1].lower()}"


def _should_escalate_quishing(
    ocr_text: str,
    *,
    domain: str,
    tld: str,
    risk_level: str,
    url_shorteners: set[str] | frozenset[str],
    suspicious_tlds: set[str] | frozenset[str],
) -> bool:
    if _meaningful_text(ocr_text):
        return False
    if domain in url_shorteners:
        return True
    if tld in suspicious_tlds:
        return True
    return risk_level == "high"


@tool
def scan_image_threats(
    file_paths: Annotated[list[str], "List of image attachment paths (under /uploaded/)."],
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Scan image attachments for OCR threats and QR phishing. Provide file_paths (under /uploaded/)."""
    return _scan_image_threats_impl(file_paths, backend_factory, runtime)


def _scan_image_threats_impl(
    file_paths: list[str],
    backend_factory: Callable[[Any], Any],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    if not file_paths:
        return {
            "per_image": [],
            "url_high_risk_count": 0,
            "url_medium_risk_count": 0,
            "technical_proofs": [],
        }

    from ._helpers import SUSPICIOUS_TLDS, URL_SHORTENERS, _normalize_path  # noqa: PLC0415
    from .ocr_images import ocr_images_bytes  # noqa: PLC0415
    from .urls_body import (  # noqa: PLC0415
        _HAS_PYZBAR,
        _enhance_url_analysis,
        _get_domain,
        _scan_images_for_qr,
        score_strong_social_engineering,
    )

    technical_proofs: list[dict[str, Any]] = []

    validated: list[str] = []
    for p in file_paths:
        try:
            validated.append(_normalize_path(p))
        except ValueError as exc:
            technical_proofs.append(
                {
                    "component": "ATTACHMENT",
                    "status": "WARNING",
                    "detail": f"Invalid image attachment path rejected: {p!r} ({exc}).",
                }
            )

    if not validated:
        return {
            "per_image": [],
            "url_high_risk_count": 0,
            "url_medium_risk_count": 0,
            "technical_proofs": technical_proofs,
        }

    backend = backend_factory(runtime)
    responses = backend.download_files(validated)

    raw_images: list[bytes] = []
    for i, resp in enumerate(responses or []):
        if getattr(resp, "error", None) or not getattr(resp, "content", None):
            raw_images.append(b"")
            technical_proofs.append(
                {
                    "component": "ATTACHMENT",
                    "status": "WARNING",
                    "detail": f"Failed to load image bytes for index {i} (path={validated[i]!r}).",
                }
            )
        else:
            raw_images.append(resp.content)

    ocr_results = ocr_images_bytes(raw_images)
    ocr_by_index: dict[int, dict[str, Any]] = {}
    ocr_unavailable = False
    for item in ocr_results:
        idx = item.get("image_index")
        if item.get("analysis_unavailable"):
            ocr_unavailable = True
        if isinstance(idx, int):
            ocr_by_index[idx] = item
    if ocr_unavailable:
        technical_proofs.append(
            {
                "component": "ATTACHMENT",
                "status": "WARNING",
                "detail": "OCR analysis unavailable for one or more images (easyocr/model download/cache issue possible).",
            }
        )

    qr_by_index: dict[int, list[str]] = {}
    if not _HAS_PYZBAR:
        technical_proofs.append(
            {
                "component": "ATTACHMENT",
                "status": "WARNING",
                "detail": "QR scan unavailable (pyzbar/Pillow missing or ZBar not installed); quishing not fully analyzed.",
            }
        )
    else:
        qr_results = _scan_images_for_qr(raw_images)
        for item in qr_results or []:
            if not isinstance(item, dict):
                continue
            idx = item.get("image_index")
            url = item.get("url")
            if isinstance(idx, int) and isinstance(url, str) and url:
                qr_by_index.setdefault(idx, []).append(url)

    per_image: list[dict[str, Any]] = []
    url_high = 0
    url_medium = 0

    evidence: list[dict[str, Any]] = []
    for i in range(len(raw_images)):
        ocr_text = str(ocr_by_index.get(i, {}).get("text") or "")
        strong_se = score_strong_social_engineering(ocr_text)
        qr_urls = qr_by_index.get(i, [])

        qr_analyses: list[dict[str, Any]] = []
        for url in qr_urls:
            result: dict[str, Any] = {
                "url": url,
                "parsed": None,
                "suspicious_indicators": [],
                "indicators": [],
                "risk_level": "low",
            }
            _enhance_url_analysis(url, result)

            domain = _get_domain(url)
            tld = _get_tld(domain)
            is_shortener = domain in URL_SHORTENERS
            is_suspicious_tld = tld in SUSPICIOUS_TLDS

            escalated = _should_escalate_quishing(
                ocr_text,
                domain=domain,
                tld=tld,
                risk_level=str(result.get("risk_level") or "low"),
                url_shorteners=URL_SHORTENERS,
                suspicious_tlds=SUSPICIOUS_TLDS,
            )
            if escalated:
                result["risk_level"] = "high"
                result.setdefault("indicators", []).append(
                    "quishing_no_text_escalation"
                )
                reason_bits: list[str] = []
                if is_shortener:
                    reason_bits.append("shortlink")
                if is_suspicious_tld:
                    reason_bits.append("suspicious_tld")
                if result.get("risk_level") == "high":
                    reason_bits.append("url_high_risk")
                technical_proofs.append(
                    {
                        "component": "URL",
                        "status": "ANOMALY",
                        "detail": (
                            "Quishing escalation: image "
                            f"{i} contains QR URL with no meaningful OCR text; "
                            f"reasons={','.join(reason_bits) or 'policy'}. URL={url}"
                        ),
                    }
                )

            if result.get("risk_level") == "high":
                url_high += 1
            elif result.get("risk_level") == "medium":
                url_medium += 1

            qr_analyses.append(
                {
                    "url": url,
                    "risk_level": result.get("risk_level"),
                    "indicators": result.get("indicators") or [],
                    "domain": domain,
                    "escalated_high": bool(escalated),
                }
            )
            if result.get("risk_level") in {"high", "medium"}:
                evidence.append(
                    {
                        "signal": f"url_risk_{result.get('risk_level')}",
                        "severity": "HIGH"
                        if result.get("risk_level") == "high"
                        else "MEDIUM",
                        "confidence": "high",
                        "artifact": {
                            "type": "url",
                            "value": url,
                            "context": {"source": "qr", "image_index": i},
                        },
                        "source": "scan_image_threats_tool",
                        "detail": "QR URL analyzed from image attachment.",
                        "details": {
                            "indicators": (result.get("indicators") or [])[:20]
                        },
                    }
                )

        per_image.append(
            {
                "image_index": i,
                "ocr_text": ocr_text,
                "strong_social_engineering": strong_se,
                "qr_urls": qr_urls,
                "qr_url_analyses": qr_analyses,
            }
        )
        if strong_se.get("score", 0) and strong_se.get("risk") in {
            "HIGH",
            "MEDIUM",
        }:
            evidence.append(
                {
                    "signal": "body_social_engineering_detected",
                    "severity": "HIGH"
                    if strong_se.get("risk") == "HIGH"
                    else "MEDIUM",
                    "confidence": "medium",
                    "artifact": {
                        "type": "file",
                        "value": validated[i],
                        "context": {"image_index": i},
                    },
                    "source": "scan_image_threats_tool",
                    "detail": "Strong social engineering language detected in OCR text.",
                    "details": strong_se,
                }
            )

    return {
        "per_image": per_image,
        "url_high_risk_count": url_high,
        "url_medium_risk_count": url_medium,
        "technical_proofs": technical_proofs,
        "evidence": evidence,
    }

