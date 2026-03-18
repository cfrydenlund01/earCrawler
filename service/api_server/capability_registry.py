from __future__ import annotations

"""Helpers for the machine-readable capability registry."""

import json
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "docs" / "capability_registry.json"
_ALLOWED_STATUSES = {
    "supported",
    "optional",
    "quarantined",
    "legacy",
    "generated",
    "archival",
}
_ALLOWED_ARTIFACT_MODES = {
    "included",
    "excluded",
    "excluded_by_default",
    "documented_only",
    "not_applicable",
}


def _validate_registry(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "capability-registry.v1":
        raise ValueError("Capability registry schema_version must be capability-registry.v1.")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("Capability registry must contain a non-empty capabilities list.")

    seen_ids: set[str] = set()
    for entry in capabilities:
        if not isinstance(entry, dict):
            raise ValueError("Capability registry entries must be JSON objects.")
        capability_id = str(entry.get("id") or "").strip()
        if not capability_id:
            raise ValueError("Capability registry entries must define a non-empty id.")
        if capability_id in seen_ids:
            raise ValueError(f"Duplicate capability registry id: {capability_id}")
        seen_ids.add(capability_id)

        status = entry.get("status")
        if status not in _ALLOWED_STATUSES:
            raise ValueError(
                f"Capability {capability_id} has unsupported status {status!r}."
            )

        artifact_mode = entry.get("contract_artifacts")
        if artifact_mode not in _ALLOWED_ARTIFACT_MODES:
            raise ValueError(
                f"Capability {capability_id} has unsupported contract_artifacts "
                f"value {artifact_mode!r}."
            )

        surfaces = entry.get("surfaces")
        if not isinstance(surfaces, list) or not surfaces:
            raise ValueError(
                f"Capability {capability_id} must list at least one declared surface."
            )

        gates = entry.get("gates")
        if not isinstance(gates, list):
            raise ValueError(f"Capability {capability_id} must provide a gates list.")


def load_capability_registry() -> dict[str, Any]:
    payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    _validate_registry(payload)
    return payload


def get_capability_index() -> dict[str, dict[str, Any]]:
    registry = load_capability_registry()
    return {entry["id"]: entry for entry in registry["capabilities"]}


def build_runtime_capability_snapshot() -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for entry in load_capability_registry()["capabilities"]:
        if not entry.get("runtime_contract_visible"):
            continue
        snapshot[entry["id"]] = {
            "status": entry["status"],
            "default_posture": entry["default_posture"],
            "surfaces": list(entry["surfaces"]),
            "gates": list(entry["gates"]),
            "contract_artifacts": entry["contract_artifacts"],
        }
    return snapshot


__all__ = [
    "build_runtime_capability_snapshot",
    "get_capability_index",
    "load_capability_registry",
]
