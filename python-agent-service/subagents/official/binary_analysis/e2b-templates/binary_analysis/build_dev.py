"""Dev build script for the ``binary-analysis-ubuntu-2204-dev`` template.

Publishes a dev-tagged variant of the binary-analysis sandbox for the
smoke / integration suite.  Keeping prod and dev on separate tags means
an in-progress template change can be exercised end-to-end (notably by
``tests/integration_tests/test_e2b_smoke.py``) without touching the
production tag that live agents pull from.

Promote a successful dev build to production with ``build_prod.py`` per
``README.md`` §"Release process".

Usage:

```bash
export E2B_API_KEY="e2b_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # or put in .env
uv run python build_dev.py
```

Override the dev template tag at runtime by pointing
``BINARY_ANALYSIS_E2B_TEMPLATE`` at ``binary-analysis-ubuntu-2204-dev``
in the host environment.

Note: E2B template names cannot contain dots; the Ubuntu version is
therefore flattened to ``2204`` rather than ``22.04``.
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from e2b import AsyncTemplate, default_build_logger

from template import template

TEMPLATE_TAG = "binary-analysis-ubuntu-2204-dev"
CPU_COUNT = 4
MEMORY_MB = 1024*8


async def main() -> None:
    """Build and publish the dev template."""
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
