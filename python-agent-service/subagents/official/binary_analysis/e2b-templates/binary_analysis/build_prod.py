"""Production build script for the ``binary-analysis-ubuntu-2204`` template.

Publishes the template referenced by
:envvar:`BINARY_ANALYSIS_E2B_TEMPLATE` (default
``binary-analysis-ubuntu-2204``).  Run this **after** a successful dev
build + smoke test per ``README.md`` §"Release process".

Note: E2B template names cannot contain dots; the Ubuntu version is
therefore flattened to ``2204`` rather than ``22.04``.

Usage:

```bash
export E2B_API_KEY="e2b_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # or put in .env
uv run python build_prod.py
```

CPU / memory are sized for Ghidra ``analyzeHeadless``
(CPU-bound, ~2-3 GB resident).  Adjust if your deployment profile differs.
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from e2b import AsyncTemplate, default_build_logger

from template import template

TEMPLATE_TAG = "binary-analysis-ubuntu-2204"
CPU_COUNT = 4
MEMORY_MB = 1024*8


async def main() -> None:
    """Build and publish the production template."""
    await AsyncTemplate.build(
        template,
        TEMPLATE_TAG,
        cpu_count=CPU_COUNT,
        memory_mb=MEMORY_MB,
        on_build_logs=default_build_logger(),
    )


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
