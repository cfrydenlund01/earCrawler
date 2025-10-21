from __future__ import annotations

"""Health endpoint implementation with readiness subchecks."""

import asyncio
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request

from earCrawler.observability.config import HealthBudgets
from .limits import RateLimitExceeded, RateLimiter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service health check")
async def health(request: Request) -> Dict[str, Any]:
    obs = getattr(request.app.state, "observability", None)
    budgets: HealthBudgets = getattr(obs, "health", HealthBudgets())
    readiness_checks: Dict[str, Dict[str, Any]] = {}

    fuseki_result = await _check_fuseki(request, budgets)
    readiness_checks["fuseki"] = fuseki_result

    readiness_checks["templates"] = _check_templates(request)
    readiness_checks["rate_limiter"] = _check_rate_limiter(request, budgets)
    readiness_checks["disk"] = _check_disk(budgets)

    readiness_status = "pass" if all(check["status"] == "pass" for check in readiness_checks.values()) else "fail"
    overall_status = "ok" if readiness_status == "pass" else "error"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "liveness": {"status": "pass"},
        "readiness": {
            "status": readiness_status,
            "checks": readiness_checks,
        },
    }


async def _check_fuseki(request: Request, budgets: HealthBudgets) -> Dict[str, Any]:
    gateway = request.app.state.gateway
    start = time.perf_counter()
    status = "pass"
    detail: Dict[str, Any] = {"template": "entity_by_id"}
    latency_ms = 0.0
    try:
        await asyncio.wait_for(
            gateway.select_as_raw("entity_by_id", {"id": "http://example.com/health"}),
            timeout=budgets.fuseki_select_ms / 1000.0,
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        if latency_ms > budgets.fuseki_select_ms:
            status = "fail"
            detail["reason"] = f"latency {latency_ms}ms > {budgets.fuseki_select_ms}ms budget"
    except Exception as exc:  # pragma: no cover - defensive
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        status = "fail"
        detail["error"] = repr(exc)
    detail["latency_ms"] = latency_ms
    return {"status": status, "details": detail}


def _check_templates(request: Request) -> Dict[str, Any]:
    registry = request.app.state.registry
    try:
        names = list(registry.names)
        status = "pass" if names else "fail"
        detail = {"templates": len(names)}
    except Exception as exc:  # pragma: no cover
        status = "fail"
        detail = {"error": repr(exc)}
    return {"status": status, "details": detail}


def _check_rate_limiter(request: Request, budgets: HealthBudgets) -> Dict[str, Any]:
    limiter: RateLimiter = request.app.state.rate_limiter
    try:
        capacity, retry_after, remaining = limiter.check("health-probe", scope="health", authenticated=True)
        status = "pass" if capacity >= budgets.rate_limit_min_capacity else "fail"
        detail = {"limit": capacity, "remaining": remaining, "retry_after": round(retry_after, 3)}
    except RateLimitExceeded as exc:  # pragma: no cover - defensive
        status = "fail"
        detail = {"limit": exc.limit, "remaining": exc.remaining, "retry_after": exc.retry_after}
    return {"status": status, "details": detail}


def _check_disk(budgets: HealthBudgets) -> Dict[str, Any]:
    usage = shutil.disk_usage(Path.cwd())
    free_mb = usage.free / (1024 * 1024)
    status = "pass" if free_mb >= budgets.disk_min_free_mb else "fail"
    detail = {"free_mb": round(free_mb, 2), "threshold_mb": budgets.disk_min_free_mb}
    if status == "fail":
        detail["reason"] = "insufficient free space"
    return {"status": status, "details": detail}


__all__ = ["router", "health"]
