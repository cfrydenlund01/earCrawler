from __future__ import annotations

import json
from pathlib import Path

from earCrawler.rag.pipeline import expand_with_kg


def test_expand_with_kg_supports_related_sections(monkeypatch, tmp_path: Path) -> None:
    mapping_path = tmp_path / "kg.json"
    mapping_path.write_text(
        json.dumps(
            {
                "740.1": {
                    "text": "License exceptions overview",
                    "source": "http://example/740",
                    "title": "License Exceptions",
                    "related_sections": ["EAR-740.9(a)(2)", "740.1"],
                    "label_hints": ["hint-a"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PATH", str(mapping_path))
    expansions = expand_with_kg(["EAR-740.1", "EAR-999.0"])
    assert len(expansions) == 1
    exp = expansions[0]
    assert exp["section_id"] == "EAR-740.1"
    assert "EAR-740.9(a)(2)" in exp["related_sections"]
    assert exp["label_hints"] == ["hint-a"]


def test_expand_with_kg_empty_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_KG_EXPANSION_PATH", raising=False)
    assert expand_with_kg(["EAR-740.1"]) == []
