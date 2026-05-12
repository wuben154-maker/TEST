"""Pytest: bundle root must shadow repo ``tests`` on sys.path for ``import tests.*``."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ROOT_STR = str(_ROOT)


def _prepend_bundle_root() -> None:
    try:
        sys.path.remove(_ROOT_STR)
    except ValueError:
        pass
    sys.path.insert(0, _ROOT_STR)


def _purge_foreign_tests_cache() -> None:
    mod = sys.modules.get("tests")
    if mod is None or not getattr(mod, "__file__", ""):
        return
    try:
        tf = Path(mod.__file__).resolve()
    except TypeError:
        return
    if tf.is_relative_to(_ROOT):
        return
    for key in list(sys.modules):
        if key == "tests" or key.startswith("tests."):
            del sys.modules[key]


_prepend_bundle_root()
_purge_foreign_tests_cache()


def pytest_configure(config: object) -> None:
    """``import-mode=prepend`` inserts repo root at ``sys.path[0]`` before test import, shadowing bundle ``tests``.

    Importlib mode avoids that path clobber; keep bundle root first for flat imports anyway.
    """
    config.option.importmode = "importlib"
    _prepend_bundle_root()
    _purge_foreign_tests_cache()
