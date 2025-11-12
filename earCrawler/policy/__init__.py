"""Policy hint loader for advisory linking rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, List

import yaml

HINTS_FILE = Path("kg/policy/hints.yml")


@dataclass(frozen=True)
class PolicyHint:
    part: str
    program: str
    priority: float
    rationale: str


def load_hints(path: Path | None = None) -> List[PolicyHint]:
    target = path or HINTS_FILE
    if not target.exists():
        return []
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    hints: List[PolicyHint] = []
    for entry in raw.get("hints", []):
        hints.append(
            PolicyHint(
                part=str(entry["part"]).strip(),
                program=str(entry["program"]).strip(),
                priority=float(entry.get("priority", 0.0)),
                rationale=str(entry.get("rationale", "")),
            )
        )
    return hints


def hints_manifest(hints: Iterable[PolicyHint]) -> str:
    serialisable = [
        hint.__dict__ for hint in sorted(hints, key=lambda h: (h.part, h.program))
    ]
    return json.dumps(serialisable, sort_keys=True)


__all__ = ["PolicyHint", "load_hints", "hints_manifest", "HINTS_FILE"]
