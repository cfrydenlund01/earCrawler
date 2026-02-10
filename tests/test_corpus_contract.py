from __future__ import annotations

import pytest

from earCrawler.rag.corpus_contract import (
    SCHEMA_VERSION,
    normalize_ear_section_id,
    require_valid_corpus,
    validate_corpus_documents,
)


def _doc(**overrides) -> dict:
    base = {
        "schema_version": SCHEMA_VERSION,
        "doc_id": "EAR-736.2",
        "section_id": "EAR-736.2",
        "text": "General prohibitions overview.",
        "chunk_kind": "section",
        "source": "ecfr_snapshot",
        "source_ref": "ecfr-2025-12-31",
    }
    base.update(overrides)
    return base


def test_valid_minimal_document_passes() -> None:
    docs = [_doc()]
    assert validate_corpus_documents(docs) == []
    require_valid_corpus(docs)  # should not raise


def test_missing_required_field_yields_issue() -> None:
    docs = [_doc()]
    docs[0].pop("section_id")
    issues = validate_corpus_documents(docs)
    assert any(issue.code == "missing_field" for issue in issues)


def test_duplicate_doc_id_detected() -> None:
    docs = [_doc(), _doc(section_id="EAR-736.2(b)", chunk_kind="subsection")]
    issues = validate_corpus_documents(docs)
    assert any(issue.code == "duplicate_doc_id" and issue.doc_index == 1 for issue in issues)


def test_normalization_examples() -> None:
    assert normalize_ear_section_id("15 CFR 736.2") == "EAR-736.2"
    assert normalize_ear_section_id("§ 736.2(b)") == "EAR-736.2(b)"
    assert normalize_ear_section_id("EAR-736.2(b)") == "EAR-736.2(b)"


def test_doc_id_suffix_allowed() -> None:
    docs = [
        _doc(
            doc_id="EAR-736.2#p0001",
            section_id="EAR-736.2",
            chunk_kind="paragraph",
        )
    ]
    assert validate_corpus_documents(docs) == []


def test_part_metadata_when_present_must_match_section() -> None:
    docs = [_doc(part="736")]
    assert validate_corpus_documents(docs) == []

    bad = [_doc(part="740")]
    issues = validate_corpus_documents(bad)
    assert any(issue.code == "part_section_mismatch" for issue in issues)


def test_invalid_ids_fail_validation() -> None:
    docs = [_doc(doc_id="736.2", section_id="736.2")]
    issues = validate_corpus_documents(docs)
    assert any(issue.code == "invalid_doc_id" for issue in issues)
    assert any(issue.code == "invalid_section_id" for issue in issues)
    with pytest.raises(ValueError):
        require_valid_corpus(docs)


def test_parent_id_must_exist_when_provided() -> None:
    docs = [
        _doc(doc_id="EAR-740.1", section_id="EAR-740.1"),
        _doc(
            doc_id="EAR-740.1(a)",
            section_id="EAR-740.1(a)",
            chunk_kind="subsection",
            parent_id="EAR-000.0",  # not present
        ),
    ]
    issues = validate_corpus_documents(docs)
    assert any(issue.code == "parent_missing" for issue in issues)


def test_parent_id_empty_string_is_invalid() -> None:
    docs = [_doc(parent_id="")]
    issues = validate_corpus_documents(docs)
    assert any(issue.code == "invalid_parent_id" for issue in issues)
