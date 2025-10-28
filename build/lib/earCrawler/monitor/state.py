"""State tracking and delta file generation for upstream monitoring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import json

from .utils import stable_hash, normalize_json


@dataclass
class WatchItem:
    """Simple representation of a watchlist item."""
    id: str
    payload: Any


def load_state(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_state(path: Path, state: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)


def update_state_and_write_delta(items: Dict[str, Any], state_path: Path, monitor_dir: Path, *, timestamp: datetime | None = None) -> Dict[str, Any]:
    """Update ``state`` with ``items`` and emit delta file for changes.

    Returns a mapping of changed item ids to their payloads.
    """
    state = load_state(state_path)
    new_state: Dict[str, str] = {}
    changed: Dict[str, Any] = {}
    for item_id, payload in items.items():
        digest = stable_hash(payload)
        new_state[item_id] = digest
        if state.get(item_id) != digest:
            changed[item_id] = payload
    write_state(state_path, new_state)
    monitor_dir.mkdir(parents=True, exist_ok=True)
    upstream_status_path = monitor_dir / "upstream-status.json"
    with upstream_status_path.open("w", encoding="utf-8") as fh:
        json.dump(new_state, fh, indent=2, sort_keys=True)
    if not changed:
        return {}
    ts = timestamp or datetime.utcnow()
    delta_path = monitor_dir / f"delta-{ts.strftime('%Y%m%d')}.json"
    with delta_path.open("w", encoding="utf-8") as fh:
        json.dump(changed, fh, indent=2, sort_keys=True)
    return changed
