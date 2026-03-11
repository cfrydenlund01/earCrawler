from __future__ import annotations

import json
from pathlib import Path

import yaml
import pytest
from pytest_socket import disable_socket, enable_socket, socket_allow_hosts

from earCrawler.perf.api_budget_gate import run_budget_gate

pytestmark = pytest.mark.enable_socket


@pytest.fixture(autouse=True)
def _allow_socket():
    socket_allow_hosts(["testserver", "localhost"])
    enable_socket()
    yield
    disable_socket()


def _write_budgets(path: Path, *, latency_budget_ms: int = 500) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "profile": "test",
                "request_timeout_ms": 50,
                "routes": {
                    "search": {
                        "runtime_status": "quarantined",
                        "method": "GET",
                        "path": "/v1/search",
                        "query": {"q": "example", "limit": 1},
                        "expected_status": 200,
                        "iterations": 3,
                        "latency_p95_ms": latency_budget_ms,
                        "max_failure_rate": 0.0,
                        "timeout": {
                            "probe_delay_ms": 80,
                            "expected_status": 504,
                            "min_latency_ms": 40,
                            "max_latency_ms": 250,
                        },
                    },
                    "rag_query": {
                        "runtime_status": "supported",
                        "method": "POST",
                        "path": "/v1/rag/query",
                        "json": {
                            "query": "export controls",
                            "include_lineage": True,
                            "top_k": 2,
                        },
                        "expected_status": 200,
                        "iterations": 3,
                        "latency_p95_ms": latency_budget_ms,
                        "max_failure_rate": 0.0,
                        "timeout": {
                            "probe_delay_ms": 80,
                            "expected_status": 504,
                            "min_latency_ms": 40,
                            "max_latency_ms": 250,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_api_budget_gate_passes(tmp_path: Path) -> None:
    budgets = tmp_path / "api_budgets.yml"
    _write_budgets(budgets)

    report = run_budget_gate(budgets)

    assert report["pass"] is True
    assert report["routes"]["search"]["pass"] is True
    assert report["routes"]["rag_query"]["pass"] is True


def test_api_budget_gate_fails_when_latency_budget_too_low(tmp_path: Path) -> None:
    budgets = tmp_path / "api_budgets.yml"
    _write_budgets(budgets, latency_budget_ms=0)

    report = run_budget_gate(budgets)

    assert report["pass"] is False
    assert (
        report["routes"]["search"]["latency"]["pass"] is False
        or report["routes"]["rag_query"]["latency"]["pass"] is False
    )
