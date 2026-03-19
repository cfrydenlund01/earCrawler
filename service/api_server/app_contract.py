from __future__ import annotations

"""Runtime contract helpers for API app startup."""

from .capability_registry import build_runtime_capability_snapshot
from .config import ApiSettings
from .rag_support import RETRIEVER_CACHE_STORAGE_SCOPE
from .runtime_state import ApiRuntimeState


def build_runtime_contract(
    settings: ApiSettings,
    *,
    capability_registry: dict[str, object],
    runtime_state: ApiRuntimeState,
) -> dict[str, object]:
    """Build the runtime contract payload exposed via /health."""

    return {
        "topology": "single_host",
        "declared_instance_count": settings.declared_instance_count,
        "multi_instance_supported": False,
        "override_active": (
            settings.allow_unsupported_multi_instance
            and settings.declared_instance_count != 1
        ),
        "runtime_state": runtime_state.contract_payload(),
        "process_local_state": {
            **runtime_state.process_local_state(),
            "retriever_cache": RETRIEVER_CACHE_STORAGE_SCOPE,
        },
        "operator_note": (
            "One Windows host and one EarCrawler API service instance are supported. "
            "Multi-instance behavior is not supported."
        ),
        "capability_registry_schema": capability_registry["schema_version"],
        "capability_registry_source": capability_registry["source_of_truth"],
        "capabilities": build_runtime_capability_snapshot(),
    }
