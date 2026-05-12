"""Phase 5 tools: deterministic risk scoring."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool

_FINDINGS_SCHEMA = """\
JSON object summarizing all analysis findings. Fields:
- auth: {spf, dkim, dmarc} each "pass"|"fail"|"softfail"|"none"|null
- url_high_risk_count: int (default 0)
- url_medium_risk_count: int (default 0)
- attachment_risks: list of risk strings, e.g. ["CRITICAL","HIGH","LOW"]
- social_engineering_score: int 0-100 (default 0)
- prompt_injection_detected: bool (default false)
- display_name_spoofing: bool (default false)
- reply_to_mismatch: bool (default false)
- mass_mailing_penalty: optional int 0-20 representing additional risk from bulk mailing characteristics
- unanalyzed_high_tier_count: int (default 0). Number of Tier1/Tier2 attachments
  (executables, scripts, Office docs, PDFs, archives, disk images) that did NOT
  receive nested binary-analysis or scan_attachment_second_pass. When > 0 the
  scorer applies an uncertainty penalty and floors the score to at least
  SUSPICIOUS so deferred deep analysis cannot be silently scored as BENIGN.\
"""


@tool
def compute_risk_score(
    findings: Annotated[str, _FINDINGS_SCHEMA],
) -> dict[str, Any]:
    """Compute deterministic risk score from a JSON summary of analysis findings."""
    try:
        data: dict[str, Any] = json.loads(findings)
    except (json.JSONDecodeError, TypeError) as exc:
        return {
            "risk_score": 50,
            "suggested_verdict": "SUSPICIOUS",
            "score_breakdown": {},
            "error": f"Invalid JSON: {exc}",
            "analysis_unavailable": True,
        }

    auth = data.get("auth") or {}
    auth_values = [auth.get("spf"), auth.get("dkim"), auth.get("dmarc")]

    auth_fail = sum(1 for v in auth_values if isinstance(v, str) and v.lower() == "fail")
    auth_softfail = sum(
        1 for v in auth_values if isinstance(v, str) and v.lower() == "softfail"
    )
    auth_pass = sum(1 for v in auth_values if isinstance(v, str) and v.lower() == "pass")

    att_risks = [
        r.upper() if isinstance(r, str) else ""
        for r in (data.get("attachment_risks") or [])
    ]
    att_critical = sum(1 for r in att_risks if r == "CRITICAL")
    att_high = sum(1 for r in att_risks if r == "HIGH")

    url_high = int(data.get("url_high_risk_count") or 0)
    url_medium = int(data.get("url_medium_risk_count") or 0)
    se_score = min(int(data.get("social_engineering_score") or 0), 100)
    pi = bool(data.get("prompt_injection_detected"))
    spoofing = bool(data.get("display_name_spoofing"))
    reply_mismatch = bool(data.get("reply_to_mismatch"))
    mass_mailing_penalty = int(data.get("mass_mailing_penalty") or 0)
    if mass_mailing_penalty < 0:
        mass_mailing_penalty = 0
    if mass_mailing_penalty > 20:
        mass_mailing_penalty = 20

    unanalyzed_high_tier = int(data.get("unanalyzed_high_tier_count") or 0)
    if unanalyzed_high_tier < 0:
        unanalyzed_high_tier = 0
    # Cap at 30 so deep-analysis uncertainty alone cannot push into MALICIOUS;
    # 8 per deferred attachment lets a single Tier1/Tier2 deferral carry weight
    # without overwhelming positive signals from other dimensions.
    unanalyzed_penalty = min(unanalyzed_high_tier * 8, 30)

    auth_penalty = auth_fail * 20 + auth_softfail * 8
    auth_bonus = min(auth_pass * 3, 9)
    url_penalty = url_high * 15 + url_medium * 5
    att_penalty = att_critical * 25 + att_high * 15
    se_penalty = se_score // 4
    pi_penalty = 30 if pi else 0
    spoof_penalty = (10 if spoofing else 0) + (8 if reply_mismatch else 0)

    raw = (
        auth_penalty
        - auth_bonus
        + url_penalty
        + att_penalty
        + se_penalty
        + pi_penalty
        + spoof_penalty
        + mass_mailing_penalty
        + unanalyzed_penalty
    )
    score = max(0, min(raw, 100))

    # Floor: any Tier1/Tier2 attachment that did not receive nested
    # binary-analysis or scan_attachment_second_pass forces the suggested
    # verdict to at least SUSPICIOUS; uncertainty must not be reported as BENIGN.
    unanalyzed_floor_applied = False
    if unanalyzed_high_tier > 0 and score < 30:
        score = 30
        unanalyzed_floor_applied = True

    if score >= 65:
        verdict = "MALICIOUS"
    elif score >= 30:
        verdict = "SUSPICIOUS"
    else:
        verdict = "BENIGN"

    result = {
        "risk_score": score,
        "suggested_verdict": verdict,
        "score_breakdown": {
            "auth_penalty": auth_penalty,
            "auth_bonus": -auth_bonus,
            "url_penalty": url_penalty,
            "attachment_penalty": att_penalty,
            "social_engineering": se_penalty,
            "prompt_injection": pi_penalty,
            "spoofing_penalty": spoof_penalty,
            "mass_mailing": mass_mailing_penalty,
            "unanalyzed_attachments": unanalyzed_penalty,
            "unanalyzed_high_tier_count": unanalyzed_high_tier,
            "unanalyzed_floor_applied": unanalyzed_floor_applied,
        },
    }
    return result

