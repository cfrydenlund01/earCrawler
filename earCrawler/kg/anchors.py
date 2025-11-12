"""Utilities for tracking part/document anchors."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


DEFAULT_ANCHOR_PATH = Path("kg/delta/part_anchors.json")


@dataclass(frozen=True)
class Anchor:
    document_id: str
    title: str
    source_url: str
    snippet: str
    publication_date: str | None = None


def _normalise_snippet(text: str) -> str:
    return " ".join((text or "").split())


class AnchorIndex:
    """Persist a deterministic mapping of part numbers to anchors."""

    def __init__(self, *, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or DEFAULT_ANCHOR_PATH
        self._anchors: Dict[str, List[Anchor]] = self._load()

    def _load(self) -> Dict[str, List[Anchor]]:
        if not self.storage_path.exists():
            return {}
        raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        anchors: Dict[str, List[Anchor]] = {}
        for part, entries in raw.items():
            anchors[part] = [Anchor(**entry) for entry in entries]
        return anchors

    def update_part(self, part: str, anchors: List[Anchor]) -> None:
        normalised = [
            Anchor(
                document_id=a.document_id,
                title=a.title.strip(),
                source_url=a.source_url.strip(),
                snippet=_normalise_snippet(a.snippet),
                publication_date=(
                    a.publication_date.strip() if a.publication_date else None
                ),
            )
            for a in anchors
        ]
        self._anchors[part] = sorted(
            normalised,
            key=lambda a: (a.document_id, a.title.lower()),
        )

    def flush(self) -> None:
        if not self._anchors:
            return
        payload = {
            part: [asdict(anchor) for anchor in anchors]
            for part, anchors in sorted(self._anchors.items())
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, part: str) -> List[Anchor]:
        return list(self._anchors.get(part, []))


__all__ = ["Anchor", "AnchorIndex"]
