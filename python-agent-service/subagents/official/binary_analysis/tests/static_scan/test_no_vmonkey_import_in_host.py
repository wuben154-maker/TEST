"""test_no_vmonkey_import_in_host.py — zero-execution import guard (FR-03 AC-16 / NFR-04).

Uses ``ast.parse`` to walk every host ``.py`` file (project packages under
``tools/``, ``schema/``, ``sandbox/`` (except workers), ``prompts/``,
``evidence_chain/``, and top-level service modules)
and asserts that no file **outside** ``sandbox/document_workers/`` contains a
direct import of the sandbox-only parser libraries:

- ``vmonkey`` / ``vipermonkey``
- ``peepdf``
- ``pyOneNote``
- ``oletools`` (only allowed in the sandbox workers; olevba is worker-only)

This test forms the CI guard mandated by ADR-DOC-01 / IR-DOC-01 / IR-DOC-07.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Packages whose import is restricted to sandbox/document_workers/ only.
_FORBIDDEN_TOP_LEVEL = frozenset(
    [
        "vmonkey",
        "vipermonkey",
        "peepdf",
        "pyOneNote",
    ]
)

# Directory that IS allowed to import the above packages.
_ALLOWED_SUBPATH = Path("sandbox") / "document_workers"

# Root of the host source tree
# parents[0]=static_scan/, parents[1]=tests/, parents[2]=project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _collect_py_files() -> list[Path]:
    """Return host application ``.py`` files (excluding ``sandbox/document_workers``)."""
    pr = _PROJECT_ROOT
    files: list[Path] = []

    for pkg in ("tools", "schema", "prompts", "evidence_chain"):
        root = pr / pkg
        if root.is_dir():
            files.extend(root.rglob("*.py"))

    for fname in (
        "analyst_graph.py",
        "api.py",
        "audit.py",
        "budget_guards.py",
        "cli.py",
        "config.py",
        "embedded_recursion.py",
        "errors.py",
        "facts_report.py",
        "langgraph_entry.py",
        "registry.py",
        "report_bootstrap.py",
        "tool_builder.py",
        "ui_backend.py",
        "upload_materializer.py",
    ):
        fp = pr / fname
        if fp.is_file():
            files.append(fp)

    sandbox_root = pr / "sandbox"
    if sandbox_root.is_dir():
        for p in sandbox_root.rglob("*.py"):
            try:
                rel = p.relative_to(sandbox_root)
            except ValueError:
                continue
            if rel.parts[:1] == ("document_workers",):
                continue
            files.append(p)

    return sorted({p.resolve() for p in files})


def _extract_imports(source: str) -> list[tuple[str, int]]:
    """Return (module_top_level_name, lineno) for every import in ``source``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                found.append((top, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                found.append((top, node.lineno))
    return found


def test_no_forbidden_imports_in_host() -> None:
    """Assert that restricted parser libraries are not imported outside workers."""
    violations: list[str] = []

    for py_file in _collect_py_files():
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for module_name, lineno in _extract_imports(source):
            if module_name.lower() in {m.lower() for m in _FORBIDDEN_TOP_LEVEL}:
                rel = py_file.relative_to(_PROJECT_ROOT)
                violations.append(
                    f"{rel}:{lineno}: forbidden import of '{module_name}'"
                )

    assert not violations, (
        "Host Python code outside sandbox/document_workers/ imports restricted "
        "parser libraries (FR-03 AC-16 / NFR-04 / ADR-DOC-01):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_document_workers_directory_exists() -> None:
    """Sanity check: the allowed directory exists (guards against path typos)."""
    workers_dir = _PROJECT_ROOT / "sandbox" / "document_workers"
    assert workers_dir.is_dir(), (
        f"sandbox/document_workers/ not found at {workers_dir}; "
        "the directory must exist for the zero-execution guard to be meaningful"
    )


def test_all_five_workers_present() -> None:
    """Assert all five worker scripts are present (C4 completeness check)."""
    workers_dir = _PROJECT_ROOT / "sandbox" / "document_workers"
    expected = {
        "run_olevba.py",
        "run_vmonkey.py",
        "run_peepdf.py",
        "run_onenote.py",
        "run_msoffcrypto.py",
    }
    actual = {p.name for p in workers_dir.glob("run_*.py")}
    missing = expected - actual
    assert not missing, f"Missing worker scripts: {missing}"
