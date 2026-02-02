from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest
import vcr
from .torch_utils import gpu_env_ok

try:
    from pytest_socket import disable_socket, enable_socket, socket_allow_hosts
except Exception:  # pragma: no cover - pytest_socket optional in some environments
    disable_socket = enable_socket = None  # type: ignore[assignment]
    socket_allow_hosts = None  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _disable_network(request: pytest.FixtureRequest):
    """Restrict network access while allowing opt-in socket usage."""

    if os.getenv("PYTEST_ALLOW_NETWORK", "0") == "1" or not (
        disable_socket and enable_socket
    ):
        yield
        return

    allow_marker = request.node.get_closest_marker(
        "enable_socket"
    ) or request.node.get_closest_marker("network")
    hosts = ["127.0.0.1", "::1"] if socket_allow_hosts else None

    if allow_marker:
        if hosts:
            socket_allow_hosts(hosts)
        enable_socket()
        try:
            yield
        finally:
            disable_socket()
    else:
        if hosts:
            socket_allow_hosts(hosts)
        disable_socket()
        try:
            yield
        finally:
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


def _finetune_requested(markexpr: str | None) -> bool:
    """Return True when finetune tests were explicitly requested via -m."""

    if not markexpr:
        return False
    tokens = [t for t in re.split(r"[ \\t\\r\\n()&|]+", markexpr) if t]
    for idx, token in enumerate(tokens):
        if token == "finetune":
            if idx > 0 and tokens[idx - 1] == "not":
                continue
            return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Opt-in gating for finetune/GPU tests."""

    markexpr = getattr(config.option, "markexpr", None)
    finetune_selected = _finetune_requested(markexpr)
    gpu_ready = gpu_env_ok() if finetune_selected else False

    skip_unrequested = pytest.mark.skip(reason="Use -m finetune to run finetune/GPU tests explicitly.")
    skip_unavailable = pytest.mark.skip(
        reason="finetune/GPU tests require EARCRAWLER_ENABLE_GPU_TESTS=1 and a working CUDA runtime."
    )

    for item in items:
        if "finetune" in item.keywords:
            if not finetune_selected:
                item.add_marker(skip_unrequested)
            elif not gpu_ready:
                item.add_marker(skip_unavailable)
