"""Prompt-layer utilities (ADR-08 · untrusted-input sanitisation).

This package owns every transformation that sits between sample-derived
strings (FR-06 string/IOC output, FR-07 decompiled literals) and the LLM
context window.  Per ADR-08 / IR-06 / NFR-10, *all* strings originating
from the untrusted sample MUST pass through :func:`sanitize` before being
embedded into any prompt.

The C14 System-Prompt assembler (``system_prompt.py``) will live in this
same package and is responsible for declaring the ``<untrusted_sample_content>``
delimiter tag as non-trusted input so the LLM does not act on its contents.
"""

from prompts.sanitize import (
    CLOSE_TAG,
    OPEN_TAG,
    TAG_NAME,
    sanitize,
)

__all__ = [
    "CLOSE_TAG",
    "OPEN_TAG",
    "TAG_NAME",
    "sanitize",
]
