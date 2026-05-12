"""Controlled URL forensics tools (best-effort, networked).

These tools are designed for *investigative* use under strict policy gating.
They intentionally avoid JavaScript execution and large content downloads.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener

from langchain_core.tools import tool

_DEFAULT_TIMEOUT_S = 10
_MAX_BYTES_DEFAULT = 65536


class _NoRedirectHandler:  # urllib expects an object with these methods
    def http_error_301(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any
    ) -> HTTPError:  # noqa: ANN401
        return HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = (
        http_error_303
    ) = http_error_307 = http_error_308 = http_error_301


def _safe_headers_subset(headers: Any) -> dict[str, str]:
    wanted = {"content-type", "server", "location", "content-length"}
    out: dict[str, str] = {}
    try:
        for k, v in headers.items():
            if str(k).lower() in wanted:
                out[str(k).lower()] = str(v)
    except Exception:
        return {}
    return out


@tool
def fetch_url_metadata(
    url: Annotated[str, "URL to fetch metadata for (no JS; limited redirects)."],
    max_hops: Annotated[int, "Maximum redirects to follow."] = 3,
    bytes_limit: Annotated[
        int, "Maximum bytes to read from final response body."
    ] = _MAX_BYTES_DEFAULT,
    timeout_s: Annotated[int, "HTTP timeout seconds."] = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Fetch HTTP metadata and redirect chain without executing JavaScript."""
    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        return {
            "ok": False,
            "analysis_unavailable": True,
            "detail": "Invalid URL scheme",
            "url": target,
        }

    hops = max(0, min(int(max_hops), 10))
    limit = max(0, min(int(bytes_limit), 256_000))
    timeout = max(1, min(int(timeout_s), 60))

    opener = build_opener(_NoRedirectHandler())

    chain: list[dict[str, Any]] = []
    current = target
    final_status: int | None = None
    final_headers: dict[str, str] = {}
    body_snippet: str | None = None

    for _ in range(hops + 1):
        req = Request(current, headers={"User-Agent": "deepagents-email-security/1.0"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200))
                hdrs = getattr(resp, "headers", {})
                subset = _safe_headers_subset(hdrs)
                chain.append({"url": current, "status": status, "headers": subset})
                final_status = status
                final_headers = subset
                raw = resp.read(limit) if limit else b""
                if raw:
                    try:
                        body_snippet = raw.decode("utf-8", errors="replace")[:2000]
                    except Exception:
                        body_snippet = None
                break
        except HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            hdrs = getattr(exc, "headers", {})
            subset = _safe_headers_subset(hdrs)
            chain.append({"url": current, "status": status, "headers": subset})
            if status in {301, 302, 303, 307, 308}:
                loc = subset.get("location") or ""
                if not loc:
                    final_status = status
                    final_headers = subset
                    break
                current = urljoin(current, loc)
                continue
            final_status = status
            final_headers = subset
            break
        except (URLError, TimeoutError) as exc:
            return {
                "ok": False,
                "analysis_unavailable": True,
                "detail": f"Fetch failed: {exc}",
                "url": target,
                "redirect_chain": chain,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "analysis_unavailable": True,
                "detail": f"Unexpected fetch error: {exc}",
                "url": target,
                "redirect_chain": chain,
            }

    return {
        "ok": True,
        "url": target,
        "final_url": chain[-1]["url"] if chain else target,
        "final_status": final_status,
        "final_headers": final_headers,
        "redirect_chain": chain,
        "body_snippet": body_snippet,
    }


@tool
def render_url_fingerprint(
    url: Annotated[str, "URL to render in an isolated browser environment (optional)."],
) -> dict[str, Any]:
    """Placeholder for isolated rendering/screenshot/DOM fingerprinting."""
    target = (url or "").strip()
    return {
        "ok": False,
        "analysis_unavailable": True,
        "detail": "render_url_fingerprint requires an external isolated browser sandbox; not configured in this example.",
        "url": target,
    }

