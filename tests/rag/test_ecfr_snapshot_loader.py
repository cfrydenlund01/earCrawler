from __future__ import annotations

from pathlib import Path

import pytest

from earCrawler.rag.corpus_contract import SCHEMA_VERSION, require_valid_corpus
from earCrawler.rag.ecfr_snapshot_loader import load_ecfr_snapshot
from earCrawler.rag.chunking import chunk_section_text


FIXTURE = Path("tests/fixtures/ecfr_snapshot_min.jsonl")


def test_snapshot_loader_returns_valid_sorted_docs() -> None:
    docs = load_ecfr_snapshot(FIXTURE)
    assert [doc["doc_id"] for doc in docs] == ["EAR-736.2", "EAR-740.9"]
    assert all(doc["schema_version"] == SCHEMA_VERSION for doc in docs)
    require_valid_corpus(docs)  # should not raise


def test_chunking_emits_section_and_subsections() -> None:
    docs = load_ecfr_snapshot(FIXTURE)
    section = docs[0]
    chunks = chunk_section_text(
        section["section_id"],
        section.get("title"),
        section["text"],
        max_chars=400,
    )
    doc_ids = [c["doc_id"] for c in chunks]
    assert doc_ids == ["EAR-736.2", "EAR-736.2(a)", "EAR-736.2(b)"]
    assert all(c["chunk_kind"] in {"section", "subsection"} for c in chunks)


def test_chunking_splits_long_text_into_paragraphs() -> None:
    long_text = (
        "Lead paragraph that is intentionally long to exceed the limit.\n\n"
        "(a) Subsection start.\n\n"
        "Paragraph one within subsection that will be split.\n\n"
        "Paragraph two still in subsection."
    )
    chunks = chunk_section_text(
        "EAR-999.1",
        "Long section",
        long_text,
        max_chars=80,
    )
    # section container + subsection container + paragraph children
    assert any(c["doc_id"] == "EAR-999.1" for c in chunks)
    assert any(c["doc_id"] == "EAR-999.1(a)" for c in chunks)
    paragraph_ids = [
        c["doc_id"]
        for c in chunks
        if c["chunk_kind"] == "paragraph" and str(c.get("parent_id") or "") == "EAR-999.1(a)"
    ]
    assert paragraph_ids == [
        "EAR-999.1(a)#p0001",
        "EAR-999.1(a)#p0002",
        "EAR-999.1(a)#p0003",
    ]
    assert all(len(c["text"]) <= 80 for c in chunks)


def test_chunking_splits_when_no_blank_lines_present() -> None:
    # eCFR renderer HTML can produce long blocks without paragraph separators.
    long_text = "(a) " + ("word " * 5000)
    chunks = chunk_section_text(
        "EAR-999.2",
        "Long section",
        long_text,
        max_chars=600,
    )
    assert any(c["chunk_kind"] == "paragraph" for c in chunks)
    assert all(len(c["text"]) <= 600 for c in chunks)


def test_chunking_emits_nested_numeric_markers() -> None:
    text = (
        "(a) Paragraph start.\n"
        "(1) First numeric.\n"
        "Details.\n"
        "(2) Second numeric.\n"
        "More details.\n"
        "(b) Another subsection.\n"
        "Tail.\n"
    )
    chunks = chunk_section_text(
        "EAR-740.9",
        "Test",
        text,
        max_chars=1000,
    )
    doc_ids = [c["doc_id"] for c in chunks]
    assert "EAR-740.9(a)" in doc_ids
    assert "EAR-740.9(a)(1)" in doc_ids
    assert "EAR-740.9(a)(2)" in doc_ids
    assert "EAR-740.9(b)" in doc_ids
