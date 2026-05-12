"""Sandbox-side document parser workers (C4 / ADR-DOC-01 / FR-03 AC-16).

Each module in this package is a **standalone script** invoked as a subprocess
inside the sandbox.  They are the *only* location in the codebase permitted to
``import vmonkey``, ``import peepdf``, or ``import pyOneNote``.

Host-side code in ``binary_analysis.tools.document_extract`` invokes these
scripts via ``SandboxClient`` and communicates exclusively through
``stdout JSON`` / ``stderr`` — there is no shared memory or direct import.

Workers
-------
- :mod:`run_olevba`      — VBA / XL4 macro extraction via ``oletools.olevba``
- :mod:`run_vmonkey`     — Tier-B VBA/VBScript simulation via ViperMonkey
- :mod:`run_peepdf`      — PDF structure, triggers, and embedded-file extraction
- :mod:`run_onenote`     — OneNote ``FileDataStoreObject`` GUID scan (+ pyOneNote)
- :mod:`run_msoffcrypto` — Encrypted Office password brute-force via msoffcrypto

JSON output contract
--------------------
Each worker prints exactly one JSON object to *stdout* and exits.  Exit code 0
means the JSON is valid; any non-zero exit also carries a ``{"error": "..."}``
object on stdout so the caller can always ``json.loads`` the output.

Security note (NFR-04 / IR-DOC-01)
-----------------------------------
Workers perform **static analysis and controlled simulation only**.  They must
never launch Office applications, execute decoded shell commands, or write to
paths outside the workspace provided on the command line.
"""
