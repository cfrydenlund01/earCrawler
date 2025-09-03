"""Helpers for converting monitor deltas into KG artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List
import json

PREFIX = "http://example.org/"


def json_to_ttl(delta_json: Path, ttl_out: Path, prov_out: Path) -> None:
    """Convert ``delta_json`` records to simple TTL and PROV files."""
    data = json.load(delta_json.open("r", encoding="utf-8"))
    ttl_lines: List[str] = []
    prov_lines: List[str] = ["@prefix prov: <http://www.w3.org/ns/prov#> ."]
    for item_id, payload in data.items():
        iri = f"{PREFIX}{item_id}"
        label = payload.get("title") or payload.get("name") or item_id
        ttl_lines.append(f"<{iri}> <{PREFIX}label> \"{label}\" .")
        prov_lines.append(f"<{iri}> a prov:Entity .")
    ttl_out.parent.mkdir(parents=True, exist_ok=True)
    ttl_out.write_text("\n".join(ttl_lines) + "\n", encoding="utf-8")
    prov_out.parent.mkdir(parents=True, exist_ok=True)
    prov_out.write_text("\n".join(prov_lines) + "\n", encoding="utf-8")


def select_impacted_queries(changed_tags: Iterable[str], tag_map: Dict[str, List[str]]) -> List[str]:
    """Return queries impacted by ``changed_tags`` given a tag map."""
    impacted: List[str] = []
    changed = set(changed_tags)
    for query, tags in tag_map.items():
        if changed.intersection(tags):
            impacted.append(query)
    return impacted
