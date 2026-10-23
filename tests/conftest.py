import pytest


@pytest.fixture
def anyio_backend():
    """Run the async tests on asyncio only (anyio's plugin would also try trio)."""
    return "asyncio"
