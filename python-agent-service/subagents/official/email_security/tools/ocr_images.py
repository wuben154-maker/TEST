"""Image OCR tooling for the email security agent (EasyOCR).

This module is intentionally lightweight at import time. Heavy dependencies
(`easyocr`, `torch`) are imported lazily inside the tool function to avoid
slowing down agent startup when OCR isn't needed.
"""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

_MAX_IMAGE_PIXELS = 2_000_000  # ~2MP guardrail to limit CPU/memory
_MAX_TEXT_CHARS = 8_000  # prevent token explosion when OCR is noisy


def _shrink_if_needed(width: int, height: int, *, max_pixels: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return width, height
    pixels = width * height
    if pixels <= max_pixels:
        return width, height
    scale = (max_pixels / pixels) ** 0.5
    return max(1, int(width * scale)), max(1, int(height * scale))


@lru_cache(maxsize=1)
def _get_reader() -> Any:
    """Create and cache a single EasyOCR reader instance."""
    import easyocr  # noqa: PLC0415

    return easyocr.Reader(["en", "ch_sim"], gpu=False)


def ocr_images_bytes(images: list[bytes]) -> list[dict[str, Any]]:
    """Run OCR on images and return extracted text per image."""
    if not images:
        return []

    try:
        from PIL import Image  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except Exception as exc:
        return [
            {
                "image_index": None,
                "text": "",
                "analysis_unavailable": True,
                "detail": f"Pillow/numpy unavailable for OCR: {exc}",
            }
        ]

    try:
        reader = _get_reader()
    except Exception as exc:
        return [
            {
                "image_index": None,
                "text": "",
                "analysis_unavailable": True,
                "detail": (
                    "easyocr initialization failed (model download/cache issue possible): "
                    f"{exc}"
                ),
            }
        ]

    out: list[dict[str, Any]] = []
    for i, raw in enumerate(images):
        try:
            img = Image.open(io.BytesIO(raw))
            img = img.convert("RGB")
            new_w, new_h = _shrink_if_needed(
                img.width, img.height, max_pixels=_MAX_IMAGE_PIXELS
            )
            if (new_w, new_h) != (img.width, img.height):
                img = img.resize((new_w, new_h))

            arr = np.asarray(img)
            results = reader.readtext(arr, detail=1)
            texts: list[str] = []
            for item in results or []:
                try:
                    text = (item[1] or "").strip()
                except Exception:
                    continue
                if text:
                    texts.append(text)
            merged = "\n".join(texts).strip()
            if len(merged) > _MAX_TEXT_CHARS:
                merged = merged[:_MAX_TEXT_CHARS] + "\n...[truncated]..."
            out.append({"image_index": i, "text": merged, "detail": f"OCR lines: {len(texts)}"})
        except Exception as exc:
            out.append({"image_index": i, "text": "", "detail": f"OCR failed: {exc}"})

    return out

