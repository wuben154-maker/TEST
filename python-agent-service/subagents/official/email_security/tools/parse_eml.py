"""Phase 1 tools: parse_eml core and file listing."""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Callable
from email.errors import MessageError
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.policy import default as default_policy
from email.utils import getaddresses
from pathlib import Path
from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from ._helpers import (
    _decode_header_value,
    _error_result,
    _normalize_path,
    _safe_storage_basename,
    logger,
)


def _format_header(name: str, value: str) -> str:
    """Format a single header line for ``headers_raw``."""
    return f"{name}: {value}\r\n"


def _extract_headers_raw(msg: Message) -> str:
    """Build raw headers string from parsed message (fallback)."""
    lines: list[str] = []
    for name, value in msg.items():
        if value:
            lines.append(_format_header(name, value))
    return "".join(lines) if lines else ""


def _attachment_iter(msg: Message) -> list[Message]:
    """Return attachment-like parts from a parsed message.

    Includes parts with explicit ``Content-Disposition: attachment`` or ``inline``
    AND parts that lack disposition but carry a filename (some mail clients omit
    the disposition header on embedded files).
    """
    if hasattr(msg, "iter_attachments"):
        try:
            return list(msg.iter_attachments())  # type: ignore[attr-defined]
        except KeyError:
            pass
    attachments: list[Message] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition in {"attachment", "inline"}:
            attachments.append(part)
        elif filename and disposition is None:
            attachments.append(part)
    return attachments


def _count_recipients(*headers: str | None) -> int:
    """Return total recipient count across any combination of address headers."""
    parts: list[str] = []
    for value in headers:
        if value:
            parts.append(value)
    if not parts:
        return 0
    addrs = getaddresses(parts)
    return len([addr for _, addr in addrs if addr])


def _is_undisclosed_recipients(value: str | None) -> bool:
    """Heuristically detect To: undisclosed-recipients style headers."""
    if not value:
        return False
    lower = value.lower()
    # Common patterns seen in spam / bulk campaigns; keep list tight to avoid FPs.
    patterns = [
        "undisclosed-recipients",
        "undisclosed recipients",
    ]
    return any(pat in lower for pat in patterns)


def _convert_msg_to_rfc822_bytes(raw: bytes) -> bytes:
    """Convert .msg bytes into RFC822/MIME email bytes.

    This function is intentionally decoupled from any particular .msg parsing
    library. It expects a helper capable of returning an object with at least
    the following attributes:
    - sender: str | None
    - to: str | None
    - date: str | None
    - subject: str | None
    - body: str | None           # plain text
    - html_body: str | None      # HTML body (optional)
    - attachments: iterable of objects with ``filename`` and ``data`` (bytes)

    A real implementation should plug in a library such as ``extract_msg`` by
    providing an appropriate loader in ``_load_msg_from_bytes``.
    """
    msg_obj = _load_msg_from_bytes(raw)

    from_addr = getattr(msg_obj, "sender", "") or ""
    to_addrs = getattr(msg_obj, "to", "") or ""
    date = getattr(msg_obj, "date", None)
    subject = getattr(msg_obj, "subject", "") or ""
    text_body = getattr(msg_obj, "body", None)
    html_body = getattr(msg_obj, "html_body", None)

    em = EmailMessage()
    if from_addr:
        em["From"] = from_addr
    if to_addrs:
        em["To"] = to_addrs
    if subject:
        em["Subject"] = subject
    if date:
        em["Date"] = date

    if text_body and html_body:
        em.set_content(text_body)
        em.add_alternative(html_body, subtype="html")
    elif html_body:
        em.add_alternative(html_body, subtype="html")
    else:
        em.set_content(text_body or "")

    for attachment in getattr(msg_obj, "attachments", []) or []:
        filename = getattr(attachment, "filename", None) or "attachment.bin"
        data = getattr(attachment, "data", None)
        if not isinstance(data, (bytes, bytearray)) or not data:
            continue
        ctype, _ = mimetypes.guess_type(filename)
        if ctype:
            maintype, subtype = ctype.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        em.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    return em.as_bytes()


def _load_msg_from_bytes(raw: bytes) -> Any:
    """Load a .msg file from bytes and return a lightweight message object."""
    msg = "Loading .msg bytes requires wiring a concrete .msg parser into _load_msg_from_bytes."
    raise RuntimeError(msg)


def _parse_eml_from_bytes(raw: bytes) -> dict[str, Any]:
    """Parse .eml bytes into a full structure with metadata, body, and attachments."""
    parser = BytesParser(policy=default_policy)
    msg = parser.parsebytes(raw)

    metadata: dict[str, Any] = {
        "from_address": _decode_header_value(msg.get("From")),
        "to_address": _decode_header_value(msg.get("To")),
        "subject": _decode_header_value(msg.get("Subject")),
        "date": msg.get("Date"),
        "message_id": msg.get("Message-ID"),
        "reply_to": _decode_header_value(msg.get("Reply-To")),
    }

    to_header = msg.get("To")
    cc_header = msg.get("Cc")
    bcc_header = msg.get("Bcc")
    recipient_count = _count_recipients(to_header, cc_header, bcc_header)
    to_display = _decode_header_value(to_header)
    metadata["to_display"] = to_display
    metadata["recipient_count"] = recipient_count
    # Treat undisclosed-recipients headers and very large recipient lists as a bulk-mail hint.
    metadata["mass_mailing_hint"] = _is_undisclosed_recipients(to_header) or recipient_count >= 50

    header_end = raw.find(b"\r\n\r\n")
    if header_end == -1:
        header_end = raw.find(b"\n\n")
    if header_end != -1:
        headers_raw = raw[:header_end].decode("utf-8", errors="replace")
    else:
        headers_raw = _extract_headers_raw(msg)

    body_texts: list[str] = []
    body_htmls: list[str] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        ct = part.get_content_type()
        disp = part.get_content_disposition()
        if disp == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            decoded = payload.decode("utf-8", errors="replace")
        if ct == "text/plain":
            body_texts.append(decoded)
        elif ct == "text/html":
            body_htmls.append(decoded)

    body_text: str | None = "\n---\n".join(body_texts) if body_texts else None
    body_html: str | None = body_htmls[-1] if body_htmls else None

    attachments: list[dict[str, Any]] = []
    for idx, part in enumerate(_attachment_iter(msg)):
        filename = part.get_filename() or f"attachment-{idx + 1}"
        raw_payload = part.get_payload(decode=True)
        payload_bytes = raw_payload if isinstance(raw_payload, bytes) else b""  # type: ignore[assignment]
        size = len(payload_bytes)
        sha256 = hashlib.sha256(payload_bytes).hexdigest() if payload_bytes else ""

        attachments.append(
            {
                "filename": filename,
                "content_type": part.get_content_type(),
                "content_base64": None,
                "size_bytes": size,
                "sha256": sha256,
                "is_inline": part.get_content_disposition() == "inline",
                "truncated": False,
                "_payload_bytes": payload_bytes,
            }
        )

    logger.info(
        "Parsed email: subject=%r, attachments=%d",
        metadata.get("subject"),
        len(attachments),
    )
    return {
        "ok": True,
        "metadata": metadata,
        "headers_raw": headers_raw,
        "body_text": body_text,
        "body_html": body_html,
        "attachments": attachments,
        "error": None,
    }


def _externalize_attachments(
    result: dict[str, Any],
    *,
    backend: Any,
    eml_virtual_path: str,
) -> dict[str, Any]:
    """Upload all attachments to backend and return only metadata and file_path."""
    attachments = result.get("attachments")
    if not attachments:
        return result

    # Keep extracted attachments within the same owner directory as the source .eml
    # so ScopedUploadFilesystemBackend allows subsequent reads.
    base_name = Path(eml_virtual_path).name or "email"
    eml_parent = str(Path(eml_virtual_path).parent).replace("\\", "/")
    base_dir = f"{eml_parent}/attachments/{base_name}"

    new_attachments: list[dict[str, Any]] = []
    uploads: list[tuple[str, bytes]] = []

    for idx, att in enumerate(attachments):
        payload_bytes = att.get("_payload_bytes")
        if not isinstance(payload_bytes, bytes):
            payload_bytes = b""

        filename = att.get("filename") or f"attachment-{idx + 1}"
        content_type = att.get("content_type") or "application/octet-stream"
        size = int(att.get("size_bytes") or 0)
        sha256 = att.get("sha256") or ""
        is_inline = bool(att.get("is_inline"))

        storage_name = _safe_storage_basename(filename)
        prefix = sha256[:12] if sha256 else f"{idx + 1:03d}"
        file_path = f"{base_dir}/{prefix}_{storage_name}"

        uploads.append((file_path, payload_bytes))

        new_attachments.append(
            {
                "filename": filename,
                "storage_basename": storage_name,
                "content_type": content_type,
                "content_base64": None,
                "size_bytes": size,
                "sha256": sha256,
                "is_inline": is_inline,
                "truncated": False,
                "file_path": file_path,
            }
        )

    if uploads:
        try:
            backend.upload_files(uploads)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to upload extracted attachments for %s: %s",
                eml_virtual_path,
                exc,
            )

    result["attachments"] = new_attachments
    return result


@tool
def parse_eml(
    file_path: Annotated[str, "Path to the .eml file (e.g. uploaded/email.eml)."],
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> dict[str, Any]:
    """Parse an .eml email file and return full structure: metadata (From, To, Subject, Date, etc.), headers_raw, body_text, body_html, and attachments with filename, file_path (use this exact path for tools; storage_basename is the on-disk-safe name), sha256, and metadata for Phase 4 tools."""
    logger.debug("parse_eml called for path=%s", file_path)
    try:
        validated_path = _normalize_path(file_path)
    except ValueError as exc:
        return _error_result(str(exc))
    backend = backend_factory(runtime)
    responses = backend.download_files([validated_path])
    if not responses or responses[0].error:
        err = responses[0].error if responses else "file_not_found"
        return _error_result(str(err))
    content = responses[0].content
    if content is None:
        return _error_result("No content returned")
    try:
        if validated_path.lower().endswith(".msg"):
            try:
                content = _convert_msg_to_rfc822_bytes(content)
            except RuntimeError as exc:
                msg_str = str(exc)
                if "requires wiring a concrete .msg parser" in msg_str:
                    logger.info(
                        "No .msg parser wired; treating %s bytes as RFC822 email.",
                        validated_path,
                    )
                else:
                    return _error_result(f"Failed to convert .msg to RFC822: {exc}")
            except Exception as exc:  # noqa: BLE001
                return _error_result(f"Failed to convert .msg to RFC822: {exc}")

        parsed = _parse_eml_from_bytes(content)
        return _externalize_attachments(
            parsed,
            backend=backend,
            eml_virtual_path=validated_path,
        )
    except (MessageError, UnicodeDecodeError, ValueError, KeyError) as exc:
        return _error_result(f"Failed to parse email: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error parsing email: %s", exc, exc_info=True)
        return _error_result(f"Unexpected parse error: {exc}")


@tool
def list_uploaded_files(
    *,
    backend_factory: Annotated[Callable[[Any], Any], InjectedToolArg],
    runtime: ToolRuntime,
) -> list[dict[str, Any]]:
    """List all files in the /uploads/ directory with path, size, and type."""
    backend = backend_factory(runtime)
    # NOTE: The service mounts user-scoped uploads under /uploads/.
    # /uploaded was an upstream legacy prefix and is not sufficient for scoped paths.
    infos = backend.ls_info("/uploads")
    return [
        {
            "path": info.get("path", ""),
            "size": info.get("size", 0),
            "is_dir": info.get("is_dir", False),
        }
        for info in infos
    ]

