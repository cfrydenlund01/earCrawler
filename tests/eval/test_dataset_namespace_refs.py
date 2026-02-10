from __future__ import annotations

import json
import os
from pathlib import Path

from earCrawler.kg.namespaces import ENTITY_NS, LEGACY_NS_LIST, RESOURCE_NS


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _legacy_prefix(value: str) -> str | None:
    for legacy in LEGACY_NS_LIST:
        if value.startswith(legacy):
            return legacy
    return None


def test_eval_references_are_canonical() -> None:
    if os.getenv("EARCRAWLER_ALLOW_LEGACY_IRIS") == "1":
        return

    manifest_path = Path("eval") / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    refs = manifest.get("references") or {}
    for node in refs.get("kg_nodes") or []:
        assert isinstance(node, str)
        assert node.startswith(RESOURCE_NS)
        assert _legacy_prefix(node) is None

    for entry in manifest.get("datasets") or []:
        dataset_path = Path(str(entry.get("file")))
        if not dataset_path.is_absolute() and not dataset_path.exists():
            dataset_path = manifest_path.parent / dataset_path
        for item in _iter_jsonl(dataset_path):
            for ent in item.get("kg_entities") or []:
                assert isinstance(ent, str)
                assert ent.startswith(ENTITY_NS)
                assert _legacy_prefix(ent) is None
            evidence = item.get("evidence") or {}
            for node in evidence.get("kg_nodes") or []:
                assert isinstance(node, str)
                assert node.startswith(RESOURCE_NS)
                assert _legacy_prefix(node) is None

