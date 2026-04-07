from __future__ import annotations

"""Explicit ownership for API runtime state that remains process-local."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import threading
import time

from .config import ApiSettings, SUPPORTED_RUNTIME_TOPOLOGY
from .limits import RATE_LIMITER_STORAGE_SCOPE, RateLimiter
from .middleware import ConcurrencyGate, REQUEST_CONCURRENCY_STORAGE_SCOPE
from .rag_support import (
    RAG_QUERY_CACHE_STORAGE_SCOPE,
    RETRIEVER_CACHE_STORAGE_SCOPE,
    RETRIEVER_WARM_STATE_STORAGE_SCOPE,
    NullRetriever,
    RagQueryCache,
    RetrieverProtocol,
    RetrieverWarmupOutcome,
    retriever_warmup_enabled,
    retriever_warmup_timeout_seconds,
)

PROCESS_LOCAL_RUNTIME_STATE_BACKEND = "process_local"
RATE_LIMIT_RECOMMENDATION_INPUTS_STORAGE_SCOPE = "process_local"
RATE_LIMIT_RECOMMENDATION_SCHEMA_VERSION = "api-rate-limit-recommendation.v1"
_RECOMMENDATION_ROUTE_CLASSES = ("health", "query", "answer", "other")
_RECOMMENDATION_MIN_WINDOW_SECONDS = 15 * 60
_RECOMMENDATION_MIN_NON_HEALTH_REQUESTS = 200
_RECOMMENDATION_MIN_ROUTE_CLASS_REQUESTS = 20
_RECOMMENDATION_MIN_LATENCY_SECONDS = 0.25
_RECOMMENDATION_SAFETY_FACTOR = 0.70
_RECOMMENDATION_CONCURRENCY_PRESSURE_THRESHOLD = 0.05
_RECOMMENDATION_LATENCY_PRESSURE_RATIO = 0.80
_RECOMMENDATION_AUTH_SHARE = 0.25
_RECOMMENDATION_ANON_SHARE = 0.25
_RECOMMENDATION_AUTH_MIN = 40
_RECOMMENDATION_AUTH_MAX = 240
_RECOMMENDATION_ANON_MIN = 10
_RECOMMENDATION_ANON_MAX = 60


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return round(ordered[index], 3)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: int, *, low: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass(slots=True)
class RouteClassTelemetry:
    request_count: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    status_429_count: int = 0
    status_503_count: int = 0
    concurrency_saturated_count: int = 0


class RateLimitRecommendationInputs:
    """Process-local counters used to derive rate-limit recommendations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = datetime.now(timezone.utc)
        self._started_mono = time.monotonic()
        self._route_metrics = {
            route_class: RouteClassTelemetry()
            for route_class in _RECOMMENDATION_ROUTE_CLASSES
        }

    def record(
        self,
        *,
        route_class: str,
        status_code: int,
        latency_ms: float,
        concurrency_saturated: bool,
    ) -> None:
        key = route_class if route_class in self._route_metrics else "other"
        with self._lock:
            metric = self._route_metrics[key]
            metric.request_count += 1
            metric.latencies_ms.append(round(max(0.0, float(latency_ms)), 3))
            if status_code == 429:
                metric.status_429_count += 1
            if status_code == 503:
                metric.status_503_count += 1
            if concurrency_saturated:
                metric.concurrency_saturated_count += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            duration_seconds = round(max(0.0, time.monotonic() - self._started_mono), 3)
            total_requests = sum(
                metric.request_count for metric in self._route_metrics.values()
            )
            route_classes: dict[str, dict[str, object]] = {}
            for route_class in _RECOMMENDATION_ROUTE_CLASSES:
                metric = self._route_metrics[route_class]
                request_count = metric.request_count
                rate_429 = (
                    round(metric.status_429_count / request_count, 4)
                    if request_count
                    else 0.0
                )
                rate_503 = (
                    round(metric.status_503_count / request_count, 4)
                    if request_count
                    else 0.0
                )
                saturation_rate = (
                    round(metric.concurrency_saturated_count / request_count, 4)
                    if request_count
                    else 0.0
                )
                route_classes[route_class] = {
                    "request_count": request_count,
                    "p95_latency_ms": _p95(metric.latencies_ms),
                    "status_429_count": metric.status_429_count,
                    "status_503_count": metric.status_503_count,
                    "rate_429": rate_429,
                    "rate_503": rate_503,
                    "concurrency_saturated_count": metric.concurrency_saturated_count,
                    "concurrency_saturation_rate": saturation_rate,
                }
        return {
            "started_at": _iso_utc(self._started_at),
            "duration_seconds": duration_seconds,
            "total_request_count": total_requests,
            "route_classes": route_classes,
        }


@dataclass(frozen=True, slots=True)
class RateLimitRecommendationContext:
    topology: str
    declared_instance_count: int
    request_timeout_seconds: float
    concurrency_limit: int


def build_rate_limit_recommendation(
    *,
    recommendation_inputs: dict[str, object],
    runtime_state_backend: str,
    context: RateLimitRecommendationContext,
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    clamp_reasons: list[str] = []

    raw_route_classes = recommendation_inputs.get("route_classes")
    route_payload = raw_route_classes if isinstance(raw_route_classes, dict) else {}

    route_class_metrics: dict[str, dict[str, object]] = {}
    for route_class in _RECOMMENDATION_ROUTE_CLASSES:
        metrics = route_payload.get(route_class)
        metric_payload = metrics if isinstance(metrics, dict) else {}
        request_count = max(0, _safe_int(metric_payload.get("request_count")))
        p95_latency_ms = round(max(0.0, _safe_float(metric_payload.get("p95_latency_ms"))), 3)
        rate_429 = round(max(0.0, _safe_float(metric_payload.get("rate_429"))), 4)
        rate_503 = round(max(0.0, _safe_float(metric_payload.get("rate_503"))), 4)
        saturation_rate = round(
            max(0.0, _safe_float(metric_payload.get("concurrency_saturation_rate"))), 4
        )
        route_class_metrics[route_class] = {
            "request_count": request_count,
            "p95_latency_ms": p95_latency_ms,
            "rate_429": rate_429,
            "rate_503": rate_503,
            "concurrency_saturation_rate": saturation_rate,
            "eligible_for_capacity_math": (
                route_class != "health"
                and request_count >= _RECOMMENDATION_MIN_ROUTE_CLASS_REQUESTS
            ),
        }

    duration_seconds = round(
        max(0.0, _safe_float(recommendation_inputs.get("duration_seconds"))), 3
    )
    started_at = recommendation_inputs.get("started_at")
    if not isinstance(started_at, str) or not started_at:
        started_at = _iso_utc(now)
    non_health_request_count = sum(
        _safe_int(route_class_metrics[route_class]["request_count"])
        for route_class in ("query", "answer", "other")
    )
    window_eligible = (
        duration_seconds >= _RECOMMENDATION_MIN_WINDOW_SECONDS
        and non_health_request_count >= _RECOMMENDATION_MIN_NON_HEALTH_REQUESTS
    )

    unsupported_topology = (
        context.topology != SUPPORTED_RUNTIME_TOPOLOGY
        or context.declared_instance_count != 1
    )
    if unsupported_topology:
        status = "unsupported_topology"
        _append_reason(clamp_reasons, "unsupported_topology")
    elif not window_eligible:
        status = "insufficient_evidence"
        _append_reason(clamp_reasons, "insufficient_evidence")
    else:
        status = "ready"

    eligible_route_classes = [
        route_class
        for route_class in ("query", "answer", "other")
        if bool(route_class_metrics[route_class]["eligible_for_capacity_math"])
    ]
    if status == "ready" and not eligible_route_classes:
        status = "insufficient_evidence"
        _append_reason(clamp_reasons, "insufficient_evidence")

    slowest_eligible_route_class: str | None = None
    base_capacity_rpm = 0
    host_budget_rpm = 0
    penalty_multipliers = {
        "error_pressure": 1.0,
        "concurrency_pressure": 1.0,
        "latency_pressure": 1.0,
    }

    if status == "ready":
        candidate_rows: list[tuple[int, int, str, int, dict[str, float]]] = []
        route_order = {"query": 0, "answer": 1, "other": 2}
        latency_pressure_threshold_ms = (
            context.request_timeout_seconds
            * _RECOMMENDATION_LATENCY_PRESSURE_RATIO
            * 1000.0
        )
        for route_class in eligible_route_classes:
            metrics = route_class_metrics[route_class]
            p95_latency_ms = _safe_float(metrics["p95_latency_ms"])
            rate_429 = _safe_float(metrics["rate_429"])
            rate_503 = _safe_float(metrics["rate_503"])
            saturation_rate = _safe_float(metrics["concurrency_saturation_rate"])

            latency_seconds = max(
                p95_latency_ms / 1000.0, _RECOMMENDATION_MIN_LATENCY_SECONDS
            )
            base_capacity = max(
                0,
                math.floor(
                    (
                        context.concurrency_limit
                        * 60.0
                        / latency_seconds
                    )
                    * _RECOMMENDATION_SAFETY_FACTOR
                ),
            )

            error_mult = 0.50 if rate_503 > 0.0 else 1.0
            concurrency_mult = (
                0.75
                if saturation_rate > _RECOMMENDATION_CONCURRENCY_PRESSURE_THRESHOLD
                else 1.0
            )
            latency_mult = (
                0.50 if p95_latency_ms >= latency_pressure_threshold_ms else 1.0
            )
            penalized_capacity = max(
                0,
                math.floor(base_capacity * error_mult * concurrency_mult * latency_mult),
            )

            if error_mult < 1.0:
                _append_reason(clamp_reasons, "error_pressure")
            if concurrency_mult < 1.0:
                _append_reason(clamp_reasons, "concurrency_pressure")
            if latency_mult < 1.0:
                _append_reason(clamp_reasons, "latency_pressure")
            if (
                rate_429 > 0.0
                and rate_503 == 0.0
                and saturation_rate <= _RECOMMENDATION_CONCURRENCY_PRESSURE_THRESHOLD
            ):
                _append_reason(clamp_reasons, "configured_limit_binding")

            multipliers = {
                "error_pressure": error_mult,
                "concurrency_pressure": concurrency_mult,
                "latency_pressure": latency_mult,
            }
            candidate_rows.append(
                (
                    penalized_capacity,
                    route_order.get(route_class, 99),
                    route_class,
                    base_capacity,
                    multipliers,
                )
            )

        selected = min(candidate_rows, key=lambda row: (row[0], row[1]))
        host_budget_rpm = int(selected[0])
        slowest_eligible_route_class = str(selected[2])
        base_capacity_rpm = int(selected[3])
        penalty_multipliers = selected[4]

    recommended_auth_per_minute: int | None = None
    recommended_anon_per_minute: int | None = None
    if status == "ready":
        raw_auth = math.floor(host_budget_rpm * _RECOMMENDATION_AUTH_SHARE)
        if raw_auth < _RECOMMENDATION_AUTH_MIN:
            _append_reason(clamp_reasons, "min_clamp")
        if raw_auth > _RECOMMENDATION_AUTH_MAX:
            _append_reason(clamp_reasons, "max_clamp")
        recommended_auth_per_minute = _clamp_int(
            raw_auth, low=_RECOMMENDATION_AUTH_MIN, high=_RECOMMENDATION_AUTH_MAX
        )

        raw_anon = math.floor(
            recommended_auth_per_minute * _RECOMMENDATION_ANON_SHARE
        )
        if raw_anon < _RECOMMENDATION_ANON_MIN:
            _append_reason(clamp_reasons, "min_clamp")
        if raw_anon > _RECOMMENDATION_ANON_MAX:
            _append_reason(clamp_reasons, "max_clamp")
        recommended_anon_per_minute = _clamp_int(
            raw_anon, low=_RECOMMENDATION_ANON_MIN, high=_RECOMMENDATION_ANON_MAX
        )

    return {
        "schema_version": RATE_LIMIT_RECOMMENDATION_SCHEMA_VERSION,
        "generated_at": _iso_utc(now),
        "status": status,
        "observation_window": {
            "started_at": started_at,
            "ended_at": _iso_utc(now),
            "duration_seconds": duration_seconds,
            "non_health_request_count": non_health_request_count,
            "minimum_duration_seconds": _RECOMMENDATION_MIN_WINDOW_SECONDS,
            "minimum_non_health_request_count": _RECOMMENDATION_MIN_NON_HEALTH_REQUESTS,
            "window_eligible": window_eligible,
        },
        "runtime_context": {
            "topology": context.topology,
            "declared_instance_count": context.declared_instance_count,
            "runtime_state_backend": runtime_state_backend,
            "request_timeout_seconds": context.request_timeout_seconds,
            "concurrency_limit": context.concurrency_limit,
        },
        "route_class_metrics": route_class_metrics,
        "capacity_inputs": {
            "slowest_eligible_route_class": slowest_eligible_route_class,
            "safety_factor": _RECOMMENDATION_SAFETY_FACTOR,
            "base_capacity_rpm": base_capacity_rpm,
            "penalty_multipliers": penalty_multipliers,
            "host_budget_rpm": host_budget_rpm,
        },
        "recommendations": {
            "authenticated_per_minute": recommended_auth_per_minute,
            "anonymous_per_minute": recommended_anon_per_minute,
            "min_clamp": {
                "authenticated_per_minute": _RECOMMENDATION_AUTH_MIN,
                "anonymous_per_minute": _RECOMMENDATION_ANON_MIN,
            },
            "max_clamp": {
                "authenticated_per_minute": _RECOMMENDATION_AUTH_MAX,
                "anonymous_per_minute": _RECOMMENDATION_ANON_MAX,
            },
        },
        "clamp_reasons": clamp_reasons,
        "operator_override": {
            "env_vars_authoritative": True,
            "authoritative_env_vars": [
                "EARCRAWLER_API_AUTH_PER_MIN",
                "EARCRAWLER_API_ANON_PER_MIN",
            ],
            "note": (
                "Informational recommendation only. "
                "Config changes require explicit operator action."
            ),
        },
    }


@dataclass(frozen=True, slots=True)
class RuntimeStateComponent:
    storage_scope: str
    owner: str


@dataclass(slots=True)
class RetrieverRuntimeState:
    """Runtime-owned retriever state that is intentionally process-local."""

    retriever: RetrieverProtocol
    startup_warmup_requested: bool
    startup_warmup_timeout_seconds: float
    startup_warmup_status: str
    startup_warmup_reason: str | None = None

    @classmethod
    def from_retriever(
        cls, retriever: RetrieverProtocol | None = None
    ) -> "RetrieverRuntimeState":
        requested = retriever_warmup_enabled()
        return cls(
            retriever=(
                retriever
                if retriever is not None
                else NullRetriever(reason="No retriever injected")
            ),
            startup_warmup_requested=requested,
            startup_warmup_timeout_seconds=retriever_warmup_timeout_seconds(),
            startup_warmup_status="pending" if requested else "not_requested",
        )

    def record_warmup(self, outcome: RetrieverWarmupOutcome) -> None:
        self.startup_warmup_requested = outcome.requested
        self.startup_warmup_timeout_seconds = outcome.timeout_seconds
        self.startup_warmup_status = outcome.status
        self.startup_warmup_reason = outcome.reason

    def contract_payload(self) -> dict[str, object]:
        return {
            "cache_storage_scope": RETRIEVER_CACHE_STORAGE_SCOPE,
            "warm_state_storage_scope": RETRIEVER_WARM_STATE_STORAGE_SCOPE,
            "enabled": bool(getattr(self.retriever, "enabled", True)),
            "ready": bool(getattr(self.retriever, "ready", True)),
            "startup_warmup": {
                "requested": self.startup_warmup_requested,
                "status": self.startup_warmup_status,
                "timeout_seconds": self.startup_warmup_timeout_seconds,
                "reason": self.startup_warmup_reason,
            },
        }


@dataclass(slots=True)
class ApiRuntimeState:
    """Container for runtime-owned state in the supported single-host topology."""

    rate_limiter: RateLimiter
    concurrency_gate: ConcurrencyGate
    rag_query_cache: RagQueryCache
    retriever_runtime: RetrieverRuntimeState
    rate_limit_recommendation_inputs: RateLimitRecommendationInputs
    recommendation_context: RateLimitRecommendationContext
    backend: str = PROCESS_LOCAL_RUNTIME_STATE_BACKEND

    def process_local_state(self) -> dict[str, str]:
        return {
            name: component.storage_scope
            for name, component in self.components().items()
        }

    def recommendation_inputs_payload(self) -> dict[str, object]:
        payload = self.rate_limit_recommendation_inputs.snapshot()
        payload["concurrency_gate"] = self.concurrency_gate.saturation_snapshot()
        return payload

    def rate_limit_recommendation_payload(self) -> dict[str, object]:
        return build_rate_limit_recommendation(
            recommendation_inputs=self.recommendation_inputs_payload(),
            runtime_state_backend=self.backend,
            context=self.recommendation_context,
        )

    def contract_payload(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "shared_state_ready": False,
            "components": {
                name: {
                    "storage_scope": component.storage_scope,
                    "owner": component.owner,
                }
                for name, component in self.components().items()
            },
            "retriever_runtime": self.retriever_runtime.contract_payload(),
        }

    def components(self) -> dict[str, RuntimeStateComponent]:
        return {
            "rate_limits": RuntimeStateComponent(
                storage_scope=RATE_LIMITER_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "request_concurrency": RuntimeStateComponent(
                storage_scope=REQUEST_CONCURRENCY_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "rag_query_cache": RuntimeStateComponent(
                storage_scope=RAG_QUERY_CACHE_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "rate_limit_recommendation_inputs": RuntimeStateComponent(
                storage_scope=RATE_LIMIT_RECOMMENDATION_INPUTS_STORAGE_SCOPE,
                owner="runtime_state",
            ),
            "retriever_cache": RuntimeStateComponent(
                storage_scope=RETRIEVER_CACHE_STORAGE_SCOPE,
                owner="retriever_runtime",
            ),
            "retriever_warm_state": RuntimeStateComponent(
                storage_scope=RETRIEVER_WARM_STATE_STORAGE_SCOPE,
                owner="retriever_runtime",
            ),
        }


def build_process_local_runtime_state(
    settings: ApiSettings,
    *,
    rag_query_cache: RagQueryCache | None = None,
    retriever: RetrieverProtocol | None = None,
) -> ApiRuntimeState:
    return ApiRuntimeState(
        rate_limiter=RateLimiter(settings.rate_limits),
        concurrency_gate=ConcurrencyGate(settings.concurrency_limit),
        rag_query_cache=rag_query_cache or RagQueryCache(),
        retriever_runtime=RetrieverRuntimeState.from_retriever(retriever),
        rate_limit_recommendation_inputs=RateLimitRecommendationInputs(),
        recommendation_context=RateLimitRecommendationContext(
            topology=SUPPORTED_RUNTIME_TOPOLOGY,
            declared_instance_count=settings.declared_instance_count,
            request_timeout_seconds=settings.request_timeout_seconds,
            concurrency_limit=settings.concurrency_limit,
        ),
    )


__all__ = [
    "ApiRuntimeState",
    "PROCESS_LOCAL_RUNTIME_STATE_BACKEND",
    "RATE_LIMIT_RECOMMENDATION_INPUTS_STORAGE_SCOPE",
    "RATE_LIMIT_RECOMMENDATION_SCHEMA_VERSION",
    "RateLimitRecommendationContext",
    "RateLimitRecommendationInputs",
    "RetrieverRuntimeState",
    "RuntimeStateComponent",
    "build_rate_limit_recommendation",
    "build_process_local_runtime_state",
]
