"""Official BinaryAnalyst subagent bundle.

Hosted like :mod:`subagents.official.email_security`: registry YAML uses
``bundle_path: binary_analysis`` and resolves tools via
:mod:`subagents.official.binary_analysis.registry`.

Upstream modules use flat imports (``from audit import …``). Importing this
package inserts the bundle directory at the front of ``sys.path`` so those
imports keep working without rewriting the whole tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BUNDLE_ROOT = Path(__file__).resolve().parent


def _ensure_bundle_syspath() -> None:
    """Put bundle root first so flat imports and ``import tests.*`` resolve to this bundle."""
    root = str(_BUNDLE_ROOT)
    try:
        sys.path.remove(root)
    except ValueError:
        pass
    sys.path.insert(0, root)


_ensure_bundle_syspath()

__all__ = ["_BUNDLE_ROOT", "_ensure_bundle_syspath"]
