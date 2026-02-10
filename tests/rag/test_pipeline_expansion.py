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
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PROVIDER", "json_stub")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PATH", str(mapping_path))
    expansions = expand_with_kg(["EAR-740.1", "EAR-999.0"])
    assert len(expansions) == 1
    exp = expansions[0]
    assert exp.section_id == "EAR-740.1"
    assert "EAR-740.9(a)(2)" in exp.related_sections
    assert exp.paths == []


def test_expand_with_kg_empty_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_KG_EXPANSION_PROVIDER", raising=False)
    monkeypatch.delenv("EARCRAWLER_KG_EXPANSION_PATH", raising=False)
    monkeypatch.delenv("EARCRAWLER_ENABLE_KG_EXPANSION", raising=False)
    assert expand_with_kg(["EAR-740.1"]) == []


def test_expand_with_kg_logs_selected_stub_provider(monkeypatch, tmp_path: Path) -> None:
    class _FakeLogger:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        def info(self, event: str, **fields) -> None:
            self.events.append((event, fields))

        def warning(self, *_args, **_kwargs) -> None:
            return None

    mapping_path = tmp_path / "kg.json"
    mapping_path.write_text(json.dumps({"EAR-740.1": {"text": "stub"}}), encoding="utf-8")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PROVIDER", "json_stub")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PATH", str(mapping_path))

    import earCrawler.rag.pipeline as pipeline

    fake_logger = _FakeLogger()
    monkeypatch.setattr(pipeline, "_logger", fake_logger)

    expansions = pipeline.expand_with_kg(["EAR-740.1"])
    assert len(expansions) == 1
    assert ("rag.kg_expansion.provider", {"provider": "json_stub"}) in fake_logger.events
