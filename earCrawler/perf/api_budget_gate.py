from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings
from service.api_server.fuseki import StubFusekiClient
from service.api_server.rag_support import RagQueryCache


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, math.ceil(q * len(ordered)) - 1)
    return round(ordered[idx], 3)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


class _FastRetriever:
    enabled = True
    ready = True
    failure_type = None
    index_path = "fixture.faiss"
    model_name = "fixture-model"

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        return [
            {
                "id": "urn:entity:1",
                "text": f"Fixture retrieval for {prompt}",
                "score": 0.92,
                "source_url": "https://example.org/doc/1",
                "section": "734.3",
                "provider": "federalregister.gov",
            }
        ]


class _SlowRetriever(_FastRetriever):
    def __init__(self, delay_ms: int) -> None:
        self._delay_ms = delay_ms

    def query(self, prompt: str, k: int = 5) -> list[dict]:
        time.sleep(self._delay_ms / 1000.0)
        return super().query(prompt, k)


class _SlowFusekiClient(StubFusekiClient):
    def __init__(
        self, delay_ms: int, responses: dict[str, list[dict[str, Any]]]
    ) -> None:
        super().__init__(responses)
        self._delay_ms = delay_ms

    async def query(self, template, query: str):  # type: ignore[override]
        import asyncio

        await asyncio.sleep(self._delay_ms / 1000.0)
        return await super().query(template, query)


_FUSEKI_RESPONSES = {
    "search_entities": [
        {
            "entity": "urn:example:entity:1",
            "label": "Example Entity",
            "score": 0.98,
            "snippet": "Budget fixture",
        }
    ],
    "lineage_by_id": [
        {
            "source": "urn:entity:1",
            "relation": "http://www.w3.org/ns/prov#used",
            "target": "urn:artifact:1",
            "timestamp": "2024-01-01T00:00:00Z",
        }
    ],
}


@dataclass(frozen=True)
class RouteBudget:
    name: str
    runtime_status: str
    method: str
    path: str
    query: dict[str, Any]
    body: dict[str, Any] | None
    expected_status: int
    iterations: int
    latency_p95_ms: float
    max_failure_rate: float
    timeout_probe_delay_ms: int
    timeout_expected_status: int
    timeout_min_latency_ms: float
    timeout_max_latency_ms: float


def _load_budgets(path: Path) -> tuple[int, list[RouteBudget]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    timeout_ms = int(raw["request_timeout_ms"])
    routes = []
    for name, cfg in raw["routes"].items():
        routes.append(
            RouteBudget(
                name=name,
                runtime_status=str(cfg["runtime_status"]),
                method=str(cfg["method"]).upper(),
                path=str(cfg["path"]),
                query=dict(cfg.get("query") or {}),
                body=dict(cfg.get("json") or {}) or None,
                expected_status=int(cfg["expected_status"]),
                iterations=int(cfg["iterations"]),
                latency_p95_ms=float(cfg["latency_p95_ms"]),
                max_failure_rate=float(cfg["max_failure_rate"]),
                timeout_probe_delay_ms=int(cfg["timeout"]["probe_delay_ms"]),
                timeout_expected_status=int(cfg["timeout"]["expected_status"]),
                timeout_min_latency_ms=float(cfg["timeout"]["min_latency_ms"]),
                timeout_max_latency_ms=float(cfg["timeout"]["max_latency_ms"]),
            )
        )
    return timeout_ms, routes


def _build_client(
    *,
    request_timeout_ms: int,
    route_name: str,
    slow_delay_ms: int | None = None,
) -> TestClient:
    settings = ApiSettings(
        fuseki_url=None,
        request_timeout_seconds=request_timeout_ms / 1000.0,
    )
    if route_name == "search":
        fuseki_client = (
            _SlowFusekiClient(slow_delay_ms, _FUSEKI_RESPONSES)
            if slow_delay_ms is not None
            else StubFusekiClient(_FUSEKI_RESPONSES)
        )
        retriever = _FastRetriever()
    elif route_name == "rag_query":
        fuseki_client = StubFusekiClient(_FUSEKI_RESPONSES)
        retriever = (
            _SlowRetriever(slow_delay_ms)
            if slow_delay_ms is not None
            else _FastRetriever()
        )
    else:  # pragma: no cover - config guard
        raise ValueError(f"Unsupported route budget '{route_name}'")
    app = create_app(
        settings,
        fuseki_client=fuseki_client,
        retriever=retriever,
        rag_cache=RagQueryCache(ttl_seconds=0.0, max_entries=4),
    )
    return TestClient(app)


def _invoke(client: TestClient, route: RouteBudget) -> tuple[int, float]:
    start = time.perf_counter()
    if route.method == "GET":
        response = client.get(route.path, params=route.query)
    elif route.method == "POST":
        response = client.post(route.path, json=route.body)
    else:  # pragma: no cover - config guard
        raise ValueError(f"Unsupported method '{route.method}'")
    return response.status_code, _elapsed_ms(start)


def run_budget_gate(budgets_path: Path) -> dict[str, Any]:
    request_timeout_ms, routes = _load_budgets(budgets_path)
    report_routes: dict[str, Any] = {}
    overall_ok = True

    for route in routes:
        latencies: list[float] = []
        failures = 0
        with _build_client(
            request_timeout_ms=request_timeout_ms,
            route_name=route.name,
        ) as client:
            for _ in range(route.iterations):
                status, latency_ms = _invoke(client, route)
                latencies.append(latency_ms)
                if status != route.expected_status:
                    failures += 1

        failure_rate = failures / route.iterations if route.iterations else 0.0
        p95_ms = _percentile(latencies, 0.95)
        latency_ok = p95_ms <= route.latency_p95_ms
        failure_ok = failure_rate <= route.max_failure_rate

        with _build_client(
            request_timeout_ms=request_timeout_ms,
            route_name=route.name,
            slow_delay_ms=route.timeout_probe_delay_ms,
        ) as timeout_client:
            timeout_status, timeout_latency_ms = _invoke(timeout_client, route)

        timeout_ok = (
            timeout_status == route.timeout_expected_status
            and timeout_latency_ms >= route.timeout_min_latency_ms
            and timeout_latency_ms <= route.timeout_max_latency_ms
        )

        route_ok = latency_ok and failure_ok and timeout_ok
        overall_ok = overall_ok and route_ok
        report_routes[route.name] = {
            "runtime_status": route.runtime_status,
            "latency": {
                "iterations": route.iterations,
                "p95_ms": p95_ms,
                "budget_p95_ms": route.latency_p95_ms,
                "pass": latency_ok,
            },
            "failures": {
                "count": failures,
                "failure_rate": round(failure_rate, 4),
                "max_failure_rate": route.max_failure_rate,
                "pass": failure_ok,
            },
            "timeout": {
                "status_code": timeout_status,
                "expected_status": route.timeout_expected_status,
                "latency_ms": timeout_latency_ms,
                "min_latency_ms": route.timeout_min_latency_ms,
                "max_latency_ms": route.timeout_max_latency_ms,
                "pass": timeout_ok,
            },
            "pass": route_ok,
        }

    return {
        "budgets_path": str(budgets_path),
        "request_timeout_ms": request_timeout_ms,
        "routes": report_routes,
        "pass": overall_ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic API route latency/failure budget checks."
    )
    parser.add_argument(
        "--budgets",
        default="perf/config/api_route_budgets.yml",
        help="YAML budget definition path",
    )
    parser.add_argument(
        "--report",
        default="dist/perf/api_perf_smoke.json",
        help="Report output path",
    )
    args = parser.parse_args(argv)

    report = run_budget_gate(Path(args.budgets))
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["pass"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
