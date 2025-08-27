from __future__ import annotations

import os
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
