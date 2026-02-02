from __future__ import annotations

import pytest

from earCrawler.rag.output_schema import (
    DEFAULT_ALLOWED_LABELS,
    OutputSchemaError,
    parse_strict_answer_json,
)


def test_valid_json_passes() -> None:
    raw = (
        '{'
        '"label":"permitted",'
        '"answer_text":"Yes",'
        '"citations":[{"section_id":"EAR-740.1","quote":"License Exceptions intro","span_id":""}],'
        '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
        '"assumptions":[]'
        '}'
    )
    context = "[EAR-740.1] License Exceptions intro"
    parsed = parse_strict_answer_json(
        raw, allowed_labels=DEFAULT_ALLOWED_LABELS, context=context
    )
    assert parsed["answer_text"] == "Yes"
    assert parsed["label"] == "permitted"
    assert parsed["citations"][0]["section_id"] == "EAR-740.1"


def test_invalid_json_fails() -> None:
    with pytest.raises(OutputSchemaError) as excinfo:
        parse_strict_answer_json("not-json", allowed_labels=DEFAULT_ALLOWED_LABELS)
    assert excinfo.value.code == "invalid_json"
    assert excinfo.value.as_dict()["code"] == "invalid_json"


def test_extra_key_rejected() -> None:
    raw = (
        '{'
        '"label":"permitted",'
        '"answer_text":"Yes",'
        '"citations":[],'
        '"evidence_okay":{"ok":true,"reasons":[]},'
        '"assumptions":[],'
        '"extra":"nope"'
        '}'
    )
    with pytest.raises(OutputSchemaError) as excinfo:
        parse_strict_answer_json(raw, allowed_labels=DEFAULT_ALLOWED_LABELS)
    assert excinfo.value.code == "extra_key"
    assert excinfo.value.as_dict()["details"]["unexpected"] == "extra"


def test_missing_key_rejected() -> None:
    raw = '{"label":"permitted","answer_text":"Yes","citations":[],"assumptions":[]}'
    with pytest.raises(OutputSchemaError) as excinfo:
        parse_strict_answer_json(raw, allowed_labels=DEFAULT_ALLOWED_LABELS)
    assert excinfo.value.code == "missing_key"
    assert "missing" in excinfo.value.as_dict()["details"]


def test_wrong_type_rejected() -> None:
    raw = (
        '{'
        '"label":42,'
        '"answer_text":"Yes",'
        '"citations":[],'
        '"evidence_okay":{"ok":true,"reasons":[]},'
        '"assumptions":[]'
        '}'
    )
    with pytest.raises(OutputSchemaError) as excinfo:
        parse_strict_answer_json(raw, allowed_labels=DEFAULT_ALLOWED_LABELS)
    assert excinfo.value.code == "wrong_type"
    assert excinfo.value.as_dict()["details"]["key"] == "label"


def test_invalid_enum_rejected() -> None:
    raw = (
        '{'
        '"label":"maybe",'
        '"answer_text":"Yes",'
        '"citations":[],'
        '"evidence_okay":{"ok":true,"reasons":[]},'
        '"assumptions":[]'
        '}'
    )
    with pytest.raises(OutputSchemaError) as excinfo:
        parse_strict_answer_json(raw, allowed_labels=DEFAULT_ALLOWED_LABELS)
    assert excinfo.value.code == "invalid_enum"
    assert "maybe" in excinfo.value.as_dict()["details"]["label"]


def test_ungrounded_citation_requires_unanswerable() -> None:
    raw = (
        '{'
        '"label":"permitted",'
        '"answer_text":"Yes",'
        '"citations":[{"section_id":"EAR-740.1","quote":"not present","span_id":""}],'
        '"evidence_okay":{"ok":true,"reasons":[]},'
        '"assumptions":[]'
        '}'
    )
    with pytest.raises(OutputSchemaError) as excinfo:
        parse_strict_answer_json(
            raw, allowed_labels=DEFAULT_ALLOWED_LABELS, context="[EAR-740.1] License Exceptions intro"
        )
    assert excinfo.value.code == "ungrounded_citation"
