"""E2B template specification for the binary-analysis sandbox (ADR-17).

Produces the ``binary-analysis-ubuntu-2204`` template referenced by
:class:`sandbox.e2b_backend.E2BBackend` via
``BINARY_ANALYSIS_E2B_TEMPLATE``.

Versioning:

- Tool versions are pinned (Ghidra 11.0.3, DIE 3.10, Python 3.12) so analysis
  results are reproducible.
- Upgrades are published as a new template version and rolled out by bumping
  ``BINARY_ANALYSIS_E2B_TEMPLATE`` — the host package never installs a newer
  copy of these tools at runtime.

Contents (DESIGN.md §7 external dependencies + e2e02 documents):

- Ghidra 11.0.3        — FR-07 decompilation (Apache 2.0)
- DIE 3.10             — FR-05 packer signature matching (GPL, CLI only)
- UPX                  — FR-05 allowlisted UPX-family unpacking
- FLOSS (flare-floss)  — FR-06 string extraction including stackstrings
  (Apache 2.0)
- pefile / LIEF        — FR-04 PE / ELF / Mach-O parsing (MIT / Apache)
- capstone             — disassembly support for LIEF and custom scripts
- yara / yara-python   — FR-02 triage
- ssdeep / python-tlsh — FR-01 fuzzy hashing
- python-magic         — FR-01 magic-number detection
- oletools / pypdf / msoffcrypto / pdfminer / XLMMacro / pyOneNote
  (``specs/e2e02-documents/``, ``sandbox/document_workers/*``, FR-03, ADR-DOC-01)
- ViperMonkey (Git) + legacy ``peepdf==0.4.2`` (Pillow 9+; no binary wheels for
  Py3.12 on the original pin — installed via ``--no-deps`` after modern deps)
- Python 3.12          — base interpreter.  Not available from the default
  Jammy apt repo (which ships 3.10); we pull it from the
  ``ppa:deadsnakes/ppa`` archive registered in the ``run_cmd`` stage below.

A single image ``binary-analysis-ubuntu-2204`` serves both PE/ELF and Office/PDF
document flows; document parsers run only in sandbox workers, never the host
(``ADR-DOC-01`` / ``NFR-04``).

Build:

- ``uv run python build_prod.py`` (or ``e2b template build`` through the
  official CLI).  See ``README.md`` for the full publish workflow.
"""

from __future__ import annotations

from pathlib import Path

from e2b import AsyncTemplate

_TEMPLATE_DIR = Path(__file__).resolve().parent
DECOMPILE_BY_LIST_SRC = _TEMPLATE_DIR / "DecompileByList.py"
"""Ghidra headless postScript shipped alongside this template.

Installed into ``/opt/ghidra/scripts/DecompileByList.py`` so FR-07
priority-queue-driven decompilation (IR-04 / IR-05 / FR-07 AC-7) is
available to the agent without any runtime upload step. The
accompanying `ghidra-priority-queue-workflow` skill is the only
sanctioned way to invoke ``analyzeHeadless`` (see
``config/bash_whitelist.yaml`` comment block)."""

GHIDRA_VERSION = "11.0.3"
GHIDRA_BUILD_DATE = "20240410"
GHIDRA_HOME = "/opt/ghidra"
"""Pinned Ghidra installation directory used by skills and template checks."""

JAVA_HOME = "/usr/lib/jvm/java-17-openjdk-amd64"
"""Full JDK path for Ghidra headless mode.

Ghidra's launcher cannot prompt for a JDK in E2B's non-TTY environment.  The
template therefore installs a full JDK, not just a JRE, and writes this path to
Ghidra's launch properties at build time.
"""

GHIDRA_URL = (
    "https://github.com/NationalSecurityAgency/ghidra/releases/download/"
    f"Ghidra_{GHIDRA_VERSION}_build/"
    f"ghidra_{GHIDRA_VERSION}_PUBLIC_{GHIDRA_BUILD_DATE}.zip"
)

DIE_VERSION = "3.10"
DIE_DEB_URL = (
    f"https://github.com/horsicq/DIE-engine/releases/download/{DIE_VERSION}/"
    f"die_{DIE_VERSION}_Ubuntu_22.04_amd64.deb"
)

APT_PACKAGES = [
    # Base runtime + downloaders
    "curl",
    "wget",
    "unzip",
    "ca-certificates",
    # Ghidra requires JDK 17+
    "openjdk-17-jdk-headless",
    # Python 3.12 toolchain (required by pefile / tlsh / FLOSS extensions)
    "python3.12",
    "python3.12-dev",
    "python3.12-venv",  # needed to bootstrap pip via `python3.12 -m ensurepip`
    "python3-pip",  # system pip for any 3.10-facing tools (e.g. e2b SDK helpers)
    # Build essentials for native-extension wheels (tlsh / ssdeep / lxml bindings)
    "build-essential",
    # File/format utilities used in FR-01/FR-06 workflows
    "file",
    "binutils",
    # UPX-family unpacking (FR-05 AC-8). Ubuntu 22.04 ships this as upx-ucl;
    # the template exposes a stable `upx` entry point during the smoke test.
    "upx-ucl",
    # Fuzzy hashing
    "ssdeep",
    "libfuzzy-dev",
    # YARA CLI + headers for yara-python
    "yara",
    "libyara-dev",
    # python-magic backend
    "libmagic1",
]

# Binary-analysis pip dependencies (FR-01/02/04/05/06/07).
# Installed via the explicit python3.12 step below so workers and python_exec
# always use the same Python 3.12 that `update-alternatives` sets as `python3`.
PIP_BINARY_PACKAGES: list[str] = [
    "pefile",
    "lief",
    "capstone",
    "yara-python",
    "ssdeep",
    "python-tlsh",
    "python-magic",
    "flare-floss",
]

# e2e02 document-analysis pip dependencies (FR-03 / ADR-DOC-01).
# Mirrors ``[project.optional-dependencies].documents`` in pyproject.toml,
# plus packages that are sandbox-only (ViperMonkey / peepdf — see run_cmd below).
# Note: `olefile` is a transitive dependency of `oletools` and is NOT listed
# separately to avoid version conflicts.
PIP_DOCUMENT_PACKAGES: list[str] = [
    "oletools>=0.60",
    "msoffcrypto-tool>=5.0",
    "pypdf>=4.0",
    "pdfminer.six",
    "XLMMacroDeobfuscator>=0.2.0",
    "python-pptx",  # SPEC A-06: OOXML/PPTX structural analysis (FR-03 P1)
    "lxml",
    "pyOneNote",
]

# ViperMonkey has no stable PyPI sdist; install from the canonical Git fork
# recorded in ``specs/e2e02-documents/IMPL-GUIDE.md`` (FR-03 / A-01).
# Pinning to a specific commit is recommended once the sandbox image is
# promoted to production; until then HEAD is used for initial integration.
VIPERMONKEY_GIT = "git+https://github.com/kirk-sayre-work/ViperMonkey.git"

# Original PyPI peepdf==0.4.2 hard-pins ``pillow==3.2.0`` (no Py 3.12 wheel).
# We pre-install a modern Pillow and the remaining runtime deps, then install
# peepdf itself with ``--no-deps`` so pip does not downgrade Pillow.
# Workers import ``peepdf.PDFCore.PDFParser`` (not the ``peepdf-3`` fork).
PEEPDF_VERSION = "0.4.2"
PEEPDF_RUNTIME_DEPS: list[str] = [
    "Pillow>=9",
    "pycryptodome",
    "colorama",
    "jsbeautifier",
    "pythonaes",
    "future",
    "prettytable",
]


template = (
    AsyncTemplate()
    .from_ubuntu_image("22.04")
    # Ubuntu 22.04 (Jammy) ships Python 3.10 in its default apt repo.
    # ADR-17 requires Python 3.12 (FLOSS / pefile / LIEF wheels are pinned
    # against 3.12), so register the deadsnakes PPA *before* .apt_install
    # pulls python3.12 / python3.12-dev.
    .run_cmd(
        "apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
        "software-properties-common gnupg ca-certificates && "
        "add-apt-repository -y universe && "
        "add-apt-repository -y ppa:deadsnakes/ppa && "
        "apt-get update",
        user="root",
    )
    .apt_install(APT_PACKAGES)
    # Bootstrap pip for Python 3.12 (deadsnakes PPA ships python3.12 without pip)
    # and register it as the default `python3` / `python` so that:
    #   - `python3 -c ...` in python_exec_tool.py uses the right interpreter
    #   - _SANDBOX_PYTHON = "python3.12" in document_extract._run_worker() resolves
    .run_cmd(
        "python3.12 -m ensurepip --upgrade && "
        # Upgrade pip then install setuptools + wheel for Python 3.12.
        # setuptools is required by legacy packages that use setup.py and
        # import pkg_resources at build time (e.g. ssdeep, python-tlsh).
        # setuptools>=82 removed pkg_resources entirely, which breaks those
        # sdists even with --no-build-isolation — cap below 82 until upstream
        # migrates. ensurepip only ships pip; setuptools must be added explicitly.
        # cffi must be present before ``ssdeep`` metadata prep: that package's
        # setup imports the extension module, which pulls in cffi — with
        # ``--no-build-isolation`` pip does not inject build deps into the env.
        "python3.12 -m pip install --no-cache-dir --upgrade pip "
        "'setuptools>=70,<82' wheel cffi && "
        "update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 2 && "
        "update-alternatives --install /usr/bin/python python /usr/bin/python3.12 2",
        user="root",
    )
    # Install legacy source packages first with --no-build-isolation.
    # These packages (ssdeep, python-tlsh) use old-style setup.py that imports
    # `pkg_resources` at the top level.  pip >=26 creates an isolated build
    # virtual-env per package; inside that env, setuptools' build_meta.py runs
    # setup.py via `exec(code, locals())`, and `pkg_resources` fails to import
    # from the isolated path despite setuptools being present.  Bypassing
    # isolation lets pip use the global env where pkg_resources resolves
    # correctly.  Pre-built-wheel packages are unaffected by this flag.
    .run_cmd(
        "python3.12 -m pip install --no-cache-dir --no-build-isolation "
        "ssdeep python-tlsh",
        user="root",
    )
    # Install all remaining Python packages for python3.12 explicitly.
    # Using `python3.12 -m pip` instead of `.pip_install()` (which targets the
    # system pip linked to Python 3.10 on Ubuntu 22.04) ensures that both
    # binary-analysis skills (python_exec) and document workers find their
    # imports under Python 3.12.
    .run_cmd(
        "python3.12 -m pip install --no-cache-dir "
        + " ".join(
            f"'{p}'"
            for p in PIP_BINARY_PACKAGES + PIP_DOCUMENT_PACKAGES
            if p not in ("ssdeep", "python-tlsh")
        ),
        user="root",
    )
    # ViperMonkey: no PyPI sdist — install from Git (FR-03 / A-01 / ADR-DOC-01).
    # peepdf 0.4.2: install runtime deps first with a modern Pillow, then
    # install peepdf itself with --no-deps to skip the pinned pillow==3.2.0.
    .run_cmd(
        f"python3.12 -m pip install --no-cache-dir '{VIPERMONKEY_GIT}' && "
        "python3.12 -m pip install --no-cache-dir "
        + " ".join(f"'{d}'" for d in PEEPDF_RUNTIME_DEPS)
        + " && "
        f"python3.12 -m pip install --no-cache-dir --no-deps 'peepdf=={PEEPDF_VERSION}'",
        user="root",
    )
    # Install Ghidra headless at a fixed version.  analyzeHeadless is linked
    # into /usr/local/bin so skill workflows can reference it without knowing
    # the install path. The JDK override is written into Ghidra's launcher
    # properties because E2B commands run without a TTY; otherwise Ghidra tries
    # to prompt for a JDK path and exits before headless analysis starts.
    .run_cmd(
        f"curl -fsSL -o /tmp/ghidra.zip {GHIDRA_URL}",
        user="root",
    )
    .run_cmd(
        "unzip -q /tmp/ghidra.zip -d /opt/ && "
        f"mv /opt/ghidra_* {GHIDRA_HOME} && rm /tmp/ghidra.zip",
        user="root",
    )
    .run_cmd(
        f"sed -i '/^JAVA_HOME_OVERRIDE=/d' {GHIDRA_HOME}/support/launch.properties && "
        f"printf '\\nJAVA_HOME_OVERRIDE={JAVA_HOME}\\n' >> "
        f"{GHIDRA_HOME}/support/launch.properties && "
        f"ln -sf {GHIDRA_HOME}/support/analyzeHeadless "
        "/usr/local/bin/analyzeHeadless",
        user="root",
    )
    # Install the FR-07 priority-queue postScript into Ghidra's scripts
    # directory. The `ghidra-priority-queue-workflow` skill calls
    # `analyzeHeadless ... -postScript DecompileByList.py -scriptPath
    # /opt/ghidra/scripts ...` — landing the file here at build time
    # (instead of uploading per-analysis) keeps the skill's bash line
    # hermetic and survives `-deleteProject` cleanup.
    .copy(
        str(DECOMPILE_BY_LIST_SRC.relative_to(_TEMPLATE_DIR)),
        "/opt/ghidra/scripts/DecompileByList.py",
        user="root",
        mode=0o644,
    )
    # Build-time smoke test for the exact headless path used by FR-07. Import a
    # tiny system ELF instead of relying on launcher help output, which can
    # return a non-zero status even when Ghidra is correctly installed.
    .run_cmd(
        "rm -rf /tmp/ghidra-smoke && mkdir -p /tmp/ghidra-smoke && "
        f"test -x {JAVA_HOME}/bin/java && "
        f"test -x {JAVA_HOME}/bin/javac && "
        f"{JAVA_HOME}/bin/java -version && "
        f"{JAVA_HOME}/bin/javac -version && "
        f"test -f {GHIDRA_HOME}/scripts/DecompileByList.py && "
        "if ! analyzeHeadless /tmp/ghidra-smoke smoke "
        "-import /bin/true -noanalysis -deleteProject "
        ">/tmp/analyzeHeadless.smoke 2>&1; then "
        "sed -n '1,200p' /tmp/analyzeHeadless.smoke >&2; "
        "exit 1; "
        "fi && "
        "rm -rf /tmp/ghidra-smoke",
        user="root",
    )
    # Install DIE (Detect It Easy) as a .deb; the CLI entry point ``diec``
    # is used by the `detecting-commercial-packers-with-die` skill.  DIE is
    # GPL — we install it as a CLI in the VM image only, never linked into
    # the host Python process (DESIGN.md §7 licence notes).
    .run_cmd(
        f"curl -fsSL -o /tmp/die.deb {DIE_DEB_URL}",
        user="root",
    )
    .run_cmd(
        "apt-get install -y /tmp/die.deb && rm /tmp/die.deb",
        user="root",
    )
    # Smoke-test the UPX CLI exposed through bash_whitelist.yaml. Actual
    # unpacking remains gated by FR-05 evidence and never runs on the host.
    .run_cmd(
        "if command -v upx-ucl >/dev/null 2>&1 && "
        "! command -v upx >/dev/null 2>&1; then "
        "ln -sf $(command -v upx-ucl) /usr/local/bin/upx; "
        "fi && upx --version >/tmp/upx.version && test -s /tmp/upx.version",
        user="root",
    )
    # Per-analysis workspaces live under /workspace/<analysis_id>/.  The
    # top-level directory is chowned to `user` so unprivileged tools can
    # write their own subdirectories.
    .run_cmd(
        "mkdir -p /workspace && chown user:user /workspace",
        user="root",
    )
    .set_workdir("/workspace")
)
