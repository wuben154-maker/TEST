"""Static PHP deobfuscation and behavior extraction for webshell triage."""

from __future__ import annotations

import base64
import hashlib
import re
import zlib

from .models import DecodedArtifact

_B64 = r"([A-Za-z0-9+/=\s]{16,})"
_Q = r"['\"]"
_BASE64_CALL = re.compile(rf"base64_decode\s*\(\s*{_Q}{_B64}{_Q}\s*\)", re.I)
_GZINFLATE_B64 = re.compile(
    rf"gzinflate\s*\(\s*base64_decode\s*\(\s*{_Q}{_B64}{_Q}\s*\)\s*\)",
    re.I,
)
_GZUNCOMPRESS_B64 = re.compile(
    rf"gzuncompress\s*\(\s*base64_decode\s*\(\s*{_Q}{_B64}{_Q}\s*\)\s*\)",
    re.I,
)
_STR_ROT13 = re.compile(
    rf"str_rot13\s*\(\s*{_Q}(.{{8,20000}}?){_Q}\s*\)",
    re.I | re.S,
)
_CHR_CHAIN = re.compile(r"(?:chr\s*\(\s*\d{1,3}\s*\)\s*\.?\s*){4,}", re.I)
_CHR_NUM = re.compile(r"chr\s*\(\s*(\d{1,3})\s*\)", re.I)
_MAX_LAYERS = 3
_MAX_PREVIEW = 4000


def _safe_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _b64_bytes(value: str) -> bytes | None:
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 8:
        return None
    try:
        return base64.b64decode(compact, validate=False)
    except Exception:
        return None


def _inflate_raw(raw: bytes) -> bytes | None:
    for wbits in (-15, 15, 31):
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    return None


def _artifact(
    layer: int,
    location: str,
    chain: list[str],
    text: str,
) -> DecodedArtifact:
    data = text.encode("utf-8", errors="replace")
    preview = text[:_MAX_PREVIEW]
    return DecodedArtifact(
        layer=layer,
        source_location=location,
        chain=chain,
        content_sha256=hashlib.sha256(data).hexdigest(),
        preview=preview,
        truncated=len(text) > len(preview),
    )


def _decode_once(text: str, layer: int) -> list[DecodedArtifact]:
    out: list[DecodedArtifact] = []

    for regex, chain, inflate in (
        (_GZINFLATE_B64, ["base64_decode", "gzinflate"], True),
        (_GZUNCOMPRESS_B64, ["base64_decode", "gzuncompress"], True),
    ):
        for m in regex.finditer(text):
            raw = _b64_bytes(m.group(1))
            decoded = _inflate_raw(raw) if raw and inflate else raw
            if decoded:
                out.append(
                    _artifact(
                        layer,
                        f"php:decode:{m.start()}",
                        chain,
                        _safe_text(decoded),
                    )
                )

    for m in _BASE64_CALL.finditer(text):
        raw = _b64_bytes(m.group(1))
        if raw:
            out.append(
                _artifact(
                    layer,
                    f"php:decode:{m.start()}",
                    ["base64_decode"],
                    _safe_text(raw),
                )
            )

    for m in _STR_ROT13.finditer(text):
        decoded = m.group(1).translate(
            str.maketrans(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
                "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
            )
        )
        out.append(
            _artifact(
                layer,
                f"php:decode:{m.start()}",
                ["str_rot13"],
                decoded,
            )
        )

    for m in _CHR_CHAIN.finditer(text):
        chars = []
        for n in _CHR_NUM.findall(m.group(0)):
            value = int(n)
            if 0 <= value <= 255:
                chars.append(chr(value))
        if chars:
            out.append(
                _artifact(
                    layer,
                    f"php:decode:{m.start()}",
                    ["chr_concat"],
                    "".join(chars),
                )
            )

    return out


def decode_php_layers(text: str) -> list[DecodedArtifact]:
    """Decode common PHP webshell wrappers without executing PHP."""
    artifacts: list[DecodedArtifact] = []
    queue = [(text, 1)]
    seen_hashes: set[str] = set()

    while queue:
        current, layer = queue.pop(0)
        if layer > _MAX_LAYERS:
            break
        for artifact in _decode_once(current, layer):
            if artifact.content_sha256 in seen_hashes:
                continue
            seen_hashes.add(artifact.content_sha256)
            artifacts.append(artifact)
            queue.append((artifact.preview, layer + 1))

    return artifacts
