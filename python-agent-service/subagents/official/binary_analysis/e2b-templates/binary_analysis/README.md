# binary-analysis — E2B Sandbox Template

Pre-built Ubuntu 22.04 sandbox image for the DeepAgents binary-analysis
example.  The template is the execution environment for every sample-
touching tool call (`Ghidra analyzeHeadless`, `FLOSS`, `DIE`, `pefile`,
`LIEF`, `yara`, …) per ADR-05 / ADR-17.

- **Template ID:** `binary-analysis-ubuntu-2204`
  (E2B template names cannot contain dots — we flatten `22.04` to `2204`
  per the E2B [template name rules](https://e2b.mintlify.app/docs/template/names))
- **Base image:** Ubuntu 22.04 LTS
- **Network:** runtime sandboxes are always created with
  `allow_internet_access=False` (DESIGN.md §3.1 / NFR-03)
- **Pinned tool versions:** Ghidra 11.0.3 · DIE 3.10 · Python 3.12 ·
  FLOSS (latest pip release at build time)

See `template.py` for the complete apt / pip / run-cmd build list.

## Prerequisites

- An E2B account — sign up at [e2b.dev](https://e2b.dev)
- `E2B_API_KEY` available in the environment (matches the convention used
  by `binary_analysis.config.settings`). You can also drop it into a local
  `.env` next to the build scripts; both `build_dev.py` / `build_prod.py`
  call `load_dotenv()`.
- Python 3.11+ with the `e2b` SDK installed (`pip install e2b python-dotenv`)

The template consumes a few GB per build (Ghidra alone is ~400 MB); make
sure you have enough local disk for the build cache.

## Building the template

Two build scripts live in this directory (inspired by the E2B template
[quickstart](https://e2b.dev/docs/template/quickstart)):

| Script | Template tag | Purpose |
| --- | --- | --- |
| `build_dev.py` | `binary-analysis-ubuntu-2204-dev` | iterate on the image; consumed by the E2B smoke / integration suite |
| `build_prod.py` | `binary-analysis-ubuntu-2204` | production tag pulled by agents at runtime |

Both scripts share the same CPU / memory footprint (4 vCPU · 4 GB) sized
for `Ghidra analyzeHeadless`.

```bash
# 1. install the SDK
pip install e2b python-dotenv

# 2. export your API key (or drop it into ./.env)
export E2B_API_KEY="e2b_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 3. build the dev tag first, validate with the smoke suite, then promote
uv run python build_dev.py
uv run python build_prod.py
```

## Using the template

The runtime wiring is handled by
`binary_analysis.sandbox.e2b_backend.E2BBackend` — callers never touch the
SDK directly:

```python
from binary_analysis.sandbox.e2b_backend import E2BBackend

backend = E2BBackend()  # picks BINARY_ANALYSIS_E2B_TEMPLATE from settings
session = await backend.create(analysis_id="01HK...")
try:
    await backend.upload(session, f"{session.workdir}sample.bin", sample_bytes)
    result = await backend.exec(
        session,
        ["sha256sum", f"{session.workdir}sample.bin"],
        timeout=30.0,
    )
finally:
    await backend.kill(session)
```

`BINARY_ANALYSIS_E2B_TEMPLATE` can be overridden if you publish a variant
(e.g. `binary-analysis-ubuntu-2204-dev`) without editing any code.

## Release process

1. Bump pinned versions (`GHIDRA_VERSION`, `DIE_VERSION`, pip packages) in
   `template.py`.
2. Run the build for a **dev** tag first (`binary-analysis-ubuntu-2204-dev`)
   and exercise it locally with the subprocess-fallback integration tests
   swapped to the E2B backend.
3. Run the E2B smoke suite (`examples/binary_analysis/tests/integration_tests/
   test_e2b_smoke.py`) against the dev tag.
4. Promote to the production tag (`binary-analysis-ubuntu-2204`) and
   record the new version + source commit in
   `examples/binary_analysis/skills/CHANGELOG.md` under a
   "Template updates" heading.
5. Roll out by updating `BINARY_ANALYSIS_E2B_TEMPLATE` in your deployment
   configuration.  Previous template versions remain accessible in E2B for
   rollback.

## Licence notes

- **Ghidra** (Apache 2.0) — vendored only in the VM image.
- **DIE** (GPL) — installed via its upstream `.deb` and invoked only as a
  CLI subprocess inside the VM; it is never linked into the host Python
  process (DESIGN.md §7).
- **FLOSS / pefile / LIEF / yara** — permissive licences, see their
  respective upstreams.
