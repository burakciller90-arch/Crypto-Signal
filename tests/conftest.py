from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async test contracts on the runtime's declared asyncio backend."""
    return "asyncio"
