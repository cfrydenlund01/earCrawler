from __future__ import annotations

import json
from pathlib import Path

from earCrawler.kg.export_profiles import export_profiles
from earCrawler.kg.ontology import KG_SCHEMA_VERSION


def test_reference_manifest_matches_schema(tmp_path: Path) -> None:
    ttl = Path("kg/ear.ttl")
    manifest = export_profiles(ttl, tmp_path, stem="ear")

    reference = json.loads(Path("kg/ear_export_manifest.json").read_text(encoding="utf-8"))
    assert reference["version"] == KG_SCHEMA_VERSION
    assert reference["source"] == "kg/ear.ttl"
    assert reference["stem"] == "ear"
    assert manifest == reference["files"]
