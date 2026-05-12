"""Pytest: bundle root on path; drop shadowed ``tests`` if it points at repo-wide tests."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ROOT_STR = str(_ROOT)

try:
    sys.path.remove(_ROOT_STR)
except ValueError:
    pass
sys.path.insert(0, _ROOT_STR)

_t = sys.modules.get("tests")
if _t is not None and getattr(_t, "__file__", ""):
    try:
        tf = Path(_t.__file__).resolve()
    except TypeError:
        tf = None
    if tf is not None and not tf.is_relative_to(_ROOT):
        for key in list(sys.modules):
            if key == "tests" or key.startswith("tests."):
                del sys.modules[key]
