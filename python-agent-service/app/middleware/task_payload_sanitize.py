"""Sanitize file references embedded in task() delegation payloads.

Subagents resolve content via read_file / backend paths; embedding fullContent
in the JSON description duplicates tokens and leaks large blobs into logs.
"""

from __future__ import annotations

# Keys safe to pass to subagents for routing and on-disk resolution.
_FILE_REF_ALLOWLIST: frozenset[str] = frozenset(
    {
        "filename",
        "file_id",
        "artifactId",
        "artifact_id",
        "mime",
        "size",
        "sha256",
        "inputType",
        "serverPath",
        "file_path",
        "filePath",
        "hasServerPath",
    }
)


def sanitize_file_refs_for_task_payload(files: list[dict] | None) -> list[dict]:
    """Return a copy of file manifest entries with body fields stripped.

    Drops fullContent, content, and any key not in the allowlist so the main
    agent's task(description=...) stays path/metadata-oriented.

    Args:
        files: Raw entries from intent file_manifest or task context.

    Returns:
        New list of dicts suitable for JSON serialization in task payloads.
    """
    if not files:
        return []
    out: list[dict] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        slim: dict[str, object] = {
            k: item[k] for k in _FILE_REF_ALLOWLIST if k in item and k != "hasServerPath"
        }
        path_like = bool(
            item.get("serverPath") or item.get("file_path") or item.get("filePath")
        )
        if path_like:
            slim["hasServerPath"] = True
        elif "hasServerPath" in item:
            slim["hasServerPath"] = bool(item.get("hasServerPath"))
        out.append(slim)
    return out
