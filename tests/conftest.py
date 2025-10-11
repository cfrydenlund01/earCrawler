from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import vcr
from pytest_socket import disable_socket, enable_socket


@pytest.fixture(autouse=True)
def _disable_network():
    if os.getenv("PYTEST_ALLOW_NETWORK", "0") != "1":
        disable_socket()
    yield
    enable_socket()


@pytest.fixture
def recorder() -> vcr.VCR:
    cassette_dir = Path(__file__).parent / "fixtures" / "cassettes"
    return vcr.VCR(
        cassette_library_dir=str(cassette_dir),
        record_mode=os.getenv("VCR_RECORD_MODE", "none"),
    )


@pytest.fixture(scope="session")
def require_pwsh() -> None:
    """Ensure that PowerShell 7 is available before running dependent tests."""

    if shutil.which("pwsh") is None:
        pytest.fail(
            "PowerShell 7 (pwsh) is required to run these tests. Install pwsh and "
            "ensure it is on the PATH before re-running the test suite.",
            pytrace=False,
        )
