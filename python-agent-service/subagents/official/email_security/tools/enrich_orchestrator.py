"""Deterministic enrich orchestrator (single tool call)."""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import tool

from .policy import (
    Artifact,
    AuditTrace,
    Budget,
    EvidenceItem,
    EvidenceStore,
    domain_from_url,
    normalize_domain,
    normalize_sha256,
    normalize_url,
    plan_attachment_ti_actions,
    plan_bec_enrich_actions,
)
from .rdap import rdap_lookup
from .sandbox_fetch import fetch_url_metadata
from .ti_open_source import lookup_malwarebazaar, lookup_urlhaus


def _add_evidence_dicts(store: EvidenceStore, evidence: list[dict[str, Any]] | None) -> None:
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        art = e.get("artifact")
        artifact = (
            Artifact(**art)
            if isinstance(art, dict) and "type" in art and "value" in art
            else None
        )
        try:
            store.add(
                EvidenceItem(
                    signal=str(e.get("signal") or ""),
                    severity=str(e.get("severity") or "INFO"),  # type: ignore[arg-type]
                    confidence=str(e.get("confidence") or "low"),  # type: ignore[arg-type]
                    artifact=artifact,
                    source=str(e.get("source") or "run_enrich_phase"),
                    detail=str(e.get("detail") or ""),
                    details=e.get("details") or {},
                    limitations=e.get("limitations") or [],
                )
            )
        except Exception:
            continue


def _ti_result_to_evidence(
    *,
    source: str,
    artifact: Artifact | None,
    ok: bool,
    malicious: bool | None,
    query_status: str | None,
    detail: str | None,
) -> list[dict[str, Any]]:
    if not ok:
        return [
            {
                "signal": f"{source}_unavailable",
                "severity": "LOW",
                "confidence": "high",
                "artifact": (
                    {"type": artifact.type, "value": artifact.value, "context": artifact.context}
                    if artifact
                    else None
                ),
                "source": "run_enrich_phase",
                "detail": detail or f"{source} unavailable",
                "limitations": ["analysis_unavailable"],
            }
        ]
    if malicious:
        return [
            {
                "signal": f"{source}_hit",
                "severity": "HIGH",
                "confidence": "high",
                "artifact": (
                    {"type": artifact.type, "value": artifact.value, "context": artifact.context}
                    if artifact
                    else None
                ),
                "source": "run_enrich_phase",
                "detail": f"{source} reports malicious (query_status={query_status or 'unknown'}).",
                "details": {"query_status": query_status},
            }
        ]
    return [
        {
            "signal": f"{source}_no_hit",
            "severity": "INFO",
            "confidence": "low",
            "artifact": (
                {"type": artifact.type, "value": artifact.value, "context": artifact.context}
                if artifact
                else None
            ),
            "source": "run_enrich_phase",
            "detail": f"{source} reports no hit (query_status={query_status or 'unknown'}).",
            "details": {"query_status": query_status},
        }
    ]


@tool
def run_enrich_phase(
    header_result: Annotated[dict[str, Any], "Output of analyze_email_headers (structured)."],
    url_result: Annotated[dict[str, Any], "Output of analyze_all_urls (structured)."],
    attachments: Annotated[list[dict[str, Any]], "parse_eml.attachments list with file_path/filename/content_type/sha256."],
    budget_left: Annotated[int, "Remaining tool-call budget available for enrich steps."],
    top_k_urls: Annotated[int, "Maximum number of URL/domain enrich targets."] = 3,
    top_k_hashes: Annotated[int, "Maximum number of attachment hash enrich targets."] = 5,
    enable_fetch: Annotated[bool, "If true, allow controlled fetch_url_metadata for Top-1 URL."] = True,
) -> dict[str, Any]:
    """Run best-effort enrichment (TI lookups and optional fetch) for top-risk artifacts.

    This tool consumes the structured outputs of earlier phases and, within a
    bounded tool-call budget, performs additional lookups against open-source TI
    sources (e.g. URLhaus / ThreatFox / MalwareBazaar) plus optional limited
    fetch-based URL fingerprinting. It returns a merged, evidence-oriented
    structure suitable for downstream scoring and reporting.
    """
    audit = AuditTrace()
    store = EvidenceStore()

    _add_evidence_dicts(store, header_result.get("evidence") if isinstance(header_result, dict) else None)
    _add_evidence_dicts(store, url_result.get("evidence") if isinstance(url_result, dict) else None)
    for att in attachments or []:
        _add_evidence_dicts(store, att.get("evidence") if isinstance(att, dict) else None)

    remaining = max(0, int(budget_left))
    budget = Budget(tool_calls_left=remaining)

    url_analyses = (url_result.get("url_analyses") or []) if isinstance(url_result, dict) else []
    bec_actions = plan_bec_enrich_actions(
        header_analysis=header_result if isinstance(header_result, dict) else {},
        url_analyses=url_analyses,
        budget=budget,
        top_k=max(0, int(top_k_urls)),
        enable_otx=False,
    )
    hash_actions = plan_attachment_ti_actions(
        attachments=attachments or [],
        budget=budget,
        top_k=max(0, int(top_k_hashes)),
    )

    actions_executed: list[dict[str, Any]] = []
    out_evidence: list[dict[str, Any]] = []
    out_iocs: list[dict[str, Any]] = []
    out_technical_proofs: list[dict[str, Any]] = []

    seen_targets: set[tuple[str, str]] = set()

    def _consume(cost: int) -> bool:
        nonlocal remaining
        if remaining < cost:
            return False
        remaining -= cost
        return True

    for action in [*bec_actions, *hash_actions]:
        if remaining <= 0:
            audit.add_limitation("enrich_budget_exhausted")
            break
        tool_name = action.tool_name
        params = action.params or {}

        if tool_name in {"rdap_lookup"}:
            domain = normalize_domain(str(params.get("domain") or ""))
            key = (tool_name, domain)
            if not domain or key in seen_targets:
                continue
            seen_targets.add(key)
        elif tool_name in {"lookup_urlhaus"}:
            target = str(params.get("url_or_domain") or "")
            norm = normalize_url(target) if target.startswith(("http://", "https://")) else normalize_domain(target)
            key = (tool_name, norm)
            if not norm or key in seen_targets:
                continue
            seen_targets.add(key)
        elif tool_name in {"lookup_malwarebazaar"}:
            sha = normalize_sha256(str(params.get("sha256") or ""))
            key = (tool_name, sha)
            if not sha or key in seen_targets:
                continue
            seen_targets.add(key)
        else:
            continue

        if not _consume(1):
            audit.add_limitation("enrich_budget_exhausted")
            break

        audit.record_decision("enrich_action", reason=action.reason, details={"tool": tool_name, **params})

        if tool_name == "rdap_lookup":
            res = rdap_lookup.invoke({"domain": domain})
            status = "ok" if res.get("ok") else "unavailable"
            actions_executed.append({"tool_name": tool_name, "target": domain, "status": status})
            audit.record_tool_call(tool_name, target={"type": "domain", "value": domain}, status=status, summary=str(res.get("detail") or res.get("ok")))
            if not res.get("ok"):
                audit.add_limitation(f"rdap_lookup_unavailable:{res.get('detail')}")
                continue
            out_iocs.append({"type": "domain", "value": domain, "context": {"source": "rdap"}})
            out_evidence.append(
                {
                    "signal": "ti_rdap_observed",
                    "severity": "INFO",
                    "confidence": "high",
                    "artifact": {"type": "domain", "value": domain, "context": {"source": "rdap"}},
                    "source": "run_enrich_phase",
                    "detail": "RDAP lookup completed for domain.",
                    "details": {"has_payload": True},
                }
            )
            continue

        if tool_name == "lookup_urlhaus":
            res = lookup_urlhaus.invoke({"url_or_domain": target})
            status = "ok" if res.get("ok") else "unavailable"
            actions_executed.append({"tool_name": tool_name, "target": target, "status": status})
            audit.record_tool_call(tool_name, target={"type": "url", "value": target}, status=status, summary=str(res.get("query_status") or res.get("detail") or ""))
            art = Artifact(type="url" if target.startswith(("http://", "https://")) else "domain", value=target, context={"source": "urlhaus"})
            out_evidence.extend(
                _ti_result_to_evidence(
                    source="ti_urlhaus",
                    artifact=art,
                    ok=bool(res.get("ok")),
                    malicious=res.get("malicious") if isinstance(res.get("malicious"), bool) else None,
                    query_status=str(res.get("query_status") or "") if res.get("query_status") is not None else None,
                    detail=str(res.get("detail") or "") if res.get("detail") is not None else None,
                )
            )
            if res.get("ok"):
                if art.type == "url":
                    out_iocs.append({"type": "url", "value": normalize_url(target), "context": {"source": "urlhaus"}})
                    dom = domain_from_url(target)
                    if dom:
                        out_iocs.append({"type": "domain", "value": dom, "context": {"source": "urlhaus"}})
                else:
                    out_iocs.append({"type": "domain", "value": normalize_domain(target), "context": {"source": "urlhaus"}})
            else:
                audit.add_limitation(f"urlhaus_unavailable:{res.get('detail')}")
            continue

        if tool_name == "lookup_malwarebazaar":
            res = lookup_malwarebazaar.invoke({"sha256": sha})
            status = "ok" if res.get("ok") else "unavailable"
            actions_executed.append({"tool_name": tool_name, "target": sha, "status": status})
            audit.record_tool_call(tool_name, target={"type": "hash", "value": sha}, status=status, summary=str(res.get("query_status") or res.get("detail") or ""))
            art = Artifact(type="hash", value=sha, context={"source": "malwarebazaar"})
            out_evidence.extend(
                _ti_result_to_evidence(
                    source="ti_malwarebazaar",
                    artifact=art,
                    ok=bool(res.get("ok")),
                    malicious=res.get("malicious") if isinstance(res.get("malicious"), bool) else None,
                    query_status=str(res.get("query_status") or "") if res.get("query_status") is not None else None,
                    detail=str(res.get("detail") or "") if res.get("detail") is not None else None,
                )
            )
            if res.get("ok"):
                out_iocs.append({"type": "hash", "value": sha, "context": {"source": "malwarebazaar"}})
            else:
                audit.add_limitation(f"malwarebazaar_unavailable:{res.get('detail')}")
            continue

    if enable_fetch and remaining > 0 and isinstance(url_analyses, list) and url_analyses:
        best: str | None = None
        for level in ("high", "medium"):
            for u in url_analyses:
                if str(u.get("risk_level") or "") == level:
                    candidate = str(u.get("url") or "")
                    if candidate.startswith(("http://", "https://")):
                        best = candidate
                        break
            if best:
                break
        if best and _consume(1):
            audit.record_decision("controlled_fetch", reason="Top-1 suspicious URL metadata fetch", details={"url": best})
            res = fetch_url_metadata.invoke({"url": best, "max_hops": 3, "bytes_limit": 65536, "timeout_s": 10})
            status = "ok" if res.get("ok") else "unavailable"
            actions_executed.append({"tool_name": "fetch_url_metadata", "target": best, "status": status})
            audit.record_tool_call("fetch_url_metadata", target={"type": "url", "value": best}, status=status, summary=str(res.get("final_status") or res.get("detail") or ""))
            if not res.get("ok"):
                audit.add_limitation(f"fetch_url_metadata_unavailable:{res.get('detail')}")
            else:
                out_evidence.append(
                    {
                        "signal": "url_redirect_chain_observed",
                        "severity": "LOW",
                        "confidence": "high",
                        "artifact": {"type": "url", "value": normalize_url(best), "context": {"source": "fetch_url_metadata"}},
                        "source": "run_enrich_phase",
                        "detail": "Controlled fetch captured redirect chain and headers (no JS).",
                        "details": {"redirect_chain": (res.get("redirect_chain") or [])[:5], "final_status": res.get("final_status")},
                    }
                )

    _add_evidence_dicts(store, out_evidence)
    out_technical_proofs.extend(store.export_technical_proofs())
    out_technical_proofs.extend(audit.export_limitations_as_technical_proofs())

    merged_iocs = {
        (ioc.get("type"), ioc.get("value")): ioc
        for ioc in (store.export_iocs() or [])
        if isinstance(ioc, dict)
    }
    for ioc in out_iocs:
        if not isinstance(ioc, dict):
            continue
        k = (ioc.get("type"), ioc.get("value"))
        if k[0] and k[1] and k not in merged_iocs:
            merged_iocs[k] = ioc

    return {
        "ok": True,
        "budget_left_after": remaining,
        "actions_executed": actions_executed,
        "evidence": out_evidence,
        "technical_proofs": out_technical_proofs,
        "iocs": list(merged_iocs.values()),
        "audit_log": audit.export_investigation_log(max_lines=30),
        "limitations": audit.limitations,
    }

