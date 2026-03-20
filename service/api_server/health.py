from __future__ import annotations

"""Health endpoint implementation with readiness subchecks."""

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request

from earCrawler.observability.config import HealthBudgets
from .limits import RateLimitExceeded

router = APIRouter(tags=["health"])
_HEALTHY_SOURCE_STATES = {"ok", "no_results"}
_DEGRADED_SOURCE_STATES = {
    "missing_credentials",
    "upstream_unavailable",
    "invalid_response",
    "retry_exhausted",
}
_DEFAULT_STALE_AFTER_SECONDS = 24 * 60 * 60


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
    live_sources = _check_live_sources()

    readiness_status = (
        "pass"
        if all(check["status"] == "pass" for check in readiness_checks.values())
        else "fail"
    )
    overall_status = "pass" if readiness_status == "pass" else "fail"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runtime_contract": getattr(request.app.state, "runtime_contract", {}),
        "liveness": {"status": "pass"},
        "readiness": {
            "status": readiness_status,
            "checks": readiness_checks,
        },
        "live_sources": live_sources,
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
            detail["reason"] = (
                f"latency {latency_ms}ms > {budgets.fuseki_select_ms}ms budget"
            )
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
    limiter = request.app.state.runtime_state.rate_limiter
    try:
        capacity, retry_after, remaining = limiter.check(
            "health-probe", scope="health", authenticated=True
        )
        status = "pass" if capacity >= budgets.rate_limit_min_capacity else "fail"
        detail = {
            "limit": capacity,
            "remaining": remaining,
            "retry_after": round(retry_after, 3),
        }
    except RateLimitExceeded as exc:  # pragma: no cover - defensive
        status = "fail"
        detail = {
            "limit": exc.limit,
            "remaining": exc.remaining,
            "retry_after": exc.retry_after,
        }
    return {"status": status, "details": detail}


def _check_disk(budgets: HealthBudgets) -> Dict[str, Any]:
    usage = shutil.disk_usage(Path.cwd())
    free_mb = usage.free / (1024 * 1024)
    status = "pass" if free_mb >= budgets.disk_min_free_mb else "fail"
    detail = {"free_mb": round(free_mb, 2), "threshold_mb": budgets.disk_min_free_mb}
    if status == "fail":
        detail["reason"] = "insufficient free space"
    return {"status": status, "details": detail}


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_source_manifest_path() -> Path:
    configured = os.getenv("EARCRAWLER_SOURCE_MANIFEST_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path("data") / "manifest.json"


def _check_live_sources() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    manifest_path = _resolve_source_manifest_path()
    stale_after_seconds = int(
        os.getenv("EARCRAWLER_SOURCE_STALE_AFTER_SECONDS", _DEFAULT_STALE_AFTER_SECONDS)
    )
    payload: dict[str, Any] = {
        "status": "unknown",
        "manifest_path": str(manifest_path),
        "stale_after_seconds": stale_after_seconds,
        "sources": [],
        "failure_taxonomy": {
            "state_counts": {},
            "degraded_state_counts": {},
        },
        "summary": {
            "healthy": 0,
            "stale": 0,
            "degraded": 0,
            "unknown": 0,
            "partially_degraded": False,
            "partially_stale": False,
        },
    }
    if not manifest_path.exists():
        payload["reason"] = "manifest_missing"
        return payload

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        payload["reason"] = "manifest_unreadable"
        payload["error"] = repr(exc)
        return payload

    generated_at = _parse_utc_timestamp(manifest.get("generated_at"))
    if generated_at is not None:
        payload["generated_at"] = generated_at.isoformat().replace("+00:00", "Z")
        payload["manifest_age_seconds"] = round(
            max(0.0, (now - generated_at).total_seconds()), 3
        )

    raw_entries = manifest.get("upstream_status")
    if not isinstance(raw_entries, list) or not raw_entries:
        payload["reason"] = "no_upstream_status"
        return payload

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        operation = str(item.get("operation") or "").strip()
        state = str(item.get("state") or "").strip()
        observed_at = _parse_utc_timestamp(item.get("timestamp"))
        if not source or not operation or not state or observed_at is None:
            continue
        normalized = {
            "source": source,
            "operation": operation,
            "state": state,
            "timestamp": observed_at,
            "status_code": item.get("status_code"),
            "retry_attempts": item.get("retry_attempts"),
            "result_count": item.get("result_count"),
            "message": item.get("message"),
            "cache_hit": item.get("cache_hit"),
            "cache_age_seconds": item.get("cache_age_seconds"),
        }
        grouped.setdefault(source, []).append(normalized)

    if not grouped:
        payload["reason"] = "upstream_status_unusable"
        return payload

    sources: list[dict[str, Any]] = []
    overall_state_counts: dict[str, int] = {}
    for source in sorted(grouped):
        entries = grouped[source]
        state_counts: dict[str, int] = {}
        for entry in entries:
            state = str(entry["state"])
            state_counts[state] = state_counts.get(state, 0) + 1
            overall_state_counts[state] = overall_state_counts.get(state, 0) + 1
        latest_entry = max(entries, key=lambda entry: entry["timestamp"])
        latest_state = str(latest_entry["state"])
        last_checked = latest_entry["timestamp"]
        successes = [
            entry["timestamp"]
            for entry in entries
            if str(entry["state"]) in _HEALTHY_SOURCE_STATES
        ]
        last_success = max(successes) if successes else None
        source_stale = False
        source_degraded = False

        if latest_state == "missing_credentials":
            availability = "missing_credentials"
            source_degraded = True
        elif latest_state in _DEGRADED_SOURCE_STATES:
            availability = "unavailable"
            source_degraded = True
        else:
            availability = "available"

        freshness = "unknown"
        last_success_age_seconds: float | None = None
        if last_success is not None:
            last_success_age_seconds = max(0.0, (now - last_success).total_seconds())
            source_stale = last_success_age_seconds > stale_after_seconds
            freshness = "stale" if source_stale else "fresh"

        if source_degraded:
            source_status = "degraded"
        elif source_stale:
            source_status = "stale"
        else:
            source_status = "healthy"

        operations: dict[str, dict[str, Any]] = {}
        for entry in sorted(entries, key=lambda item: item["operation"]):
            op = str(entry["operation"])
            op_payload: dict[str, Any] = {
                "state": entry["state"],
                "timestamp": entry["timestamp"].isoformat().replace("+00:00", "Z"),
            }
            if entry.get("status_code") is not None:
                op_payload["status_code"] = int(entry["status_code"])
            if entry.get("retry_attempts") is not None:
                op_payload["retry_attempts"] = int(entry["retry_attempts"])
            if entry.get("result_count") is not None:
                op_payload["result_count"] = int(entry["result_count"])
            if entry.get("message") is not None:
                op_payload["message"] = str(entry["message"])
            if entry.get("cache_hit") is not None:
                op_payload["cache_hit"] = bool(entry["cache_hit"])
            if entry.get("cache_age_seconds") is not None:
                op_payload["cache_age_seconds"] = round(
                    float(entry["cache_age_seconds"]), 3
                )
            operations[op] = op_payload

        source_payload: dict[str, Any] = {
            "source": source,
            "status": source_status,
            "availability": availability,
            "freshness": freshness,
            "latest_state": latest_state,
            "last_checked_at": last_checked.isoformat().replace("+00:00", "Z"),
            "state_counts": {
                state: state_counts[state] for state in sorted(state_counts)
            },
            "operations": operations,
        }
        if last_success is not None:
            source_payload["last_success_at"] = last_success.isoformat().replace(
                "+00:00", "Z"
            )
            source_payload["last_success_age_seconds"] = round(
                float(last_success_age_seconds or 0.0), 3
            )
        latest_cache = next(
            (
                entry
                for entry in sorted(entries, key=lambda item: item["timestamp"], reverse=True)
                if entry.get("cache_age_seconds") is not None
            ),
            None,
        )
        if latest_cache is not None:
            source_payload["latest_cache_age_seconds"] = round(
                float(latest_cache["cache_age_seconds"]), 3
            )
            if latest_cache.get("cache_hit") is not None:
                source_payload["latest_cache_hit"] = bool(latest_cache["cache_hit"])
        sources.append(source_payload)

    counts = {"healthy": 0, "stale": 0, "degraded": 0, "unknown": 0}
    for source in sources:
        counts[str(source.get("status") or "unknown")] = (
            counts.get(str(source.get("status") or "unknown"), 0) + 1
        )

    partially_degraded = counts["degraded"] > 0 and (
        counts["healthy"] > 0 or counts["stale"] > 0
    )
    partially_stale = counts["stale"] > 0 and counts["healthy"] > 0 and counts["degraded"] == 0

    if counts["degraded"] > 0:
        overall_status = "degraded"
    elif counts["stale"] > 0:
        overall_status = "stale"
    elif counts["healthy"] > 0:
        overall_status = "healthy"
    else:
        overall_status = "unknown"

    payload["status"] = overall_status
    payload["sources"] = sources
    degraded_state_counts = {
        state: count
        for state, count in sorted(overall_state_counts.items())
        if state not in _HEALTHY_SOURCE_STATES
    }
    payload["failure_taxonomy"] = {
        "state_counts": {
            state: overall_state_counts[state] for state in sorted(overall_state_counts)
        },
        "degraded_state_counts": degraded_state_counts,
    }
    payload["summary"] = {
        **counts,
        "partially_degraded": partially_degraded,
        "partially_stale": partially_stale,
    }
    return payload


__all__ = ["router", "health"]
