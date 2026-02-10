from earCrawler.rag.retriever import _apply_citation_boost, _extract_ear_section_targets


def test_extract_ear_section_targets_from_citation() -> None:
    prompt = "15 CFR 740.1 \u00a7 740.1 Introduction."
    assert _extract_ear_section_targets(prompt) == ["EAR-740.1"]


def test_extract_ear_section_targets_includes_base_for_subsection() -> None:
    prompt = "See \u00a7 736.2(b)(4) for end-user restrictions."
    assert _extract_ear_section_targets(prompt) == ["EAR-736.2(b)(4)", "EAR-736.2"]


def test_apply_citation_boost_prepends_missing_section() -> None:
    metadata = [
        {"doc_id": "EAR-744.1", "text": "other"},
        {"doc_id": "EAR-740.1", "text": "intro"},
    ]
    results = [{"doc_id": "EAR-744.1", "section_id": "EAR-744.1", "score": 0.9}]
    boosted = _apply_citation_boost(
        "15 CFR 740.1 \u00a7 740.1 Introduction.",
        results=results,
        metadata=metadata,
        k=5,
    )
    assert boosted[0]["section_id"] == "EAR-740.1"


def test_apply_citation_boost_noop_when_already_present() -> None:
    metadata = [{"doc_id": "EAR-740.1", "text": "intro"}]
    results = [{"doc_id": "EAR-740.1", "section_id": "EAR-740.1", "score": 0.1}]
    boosted = _apply_citation_boost(
        "15 CFR 740.1 \u00a7 740.1 Introduction.",
        results=results,
        metadata=metadata,
        k=5,
    )
    assert boosted == results

