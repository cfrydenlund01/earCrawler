from __future__ import annotations

import pytest

from earCrawler.eval.groundedness_gates import (
    DEFAULT_PHASE2_GATES_PATH,
    load_phase2_gate_thresholds,
)


def test_default_phase2_gates_file_exists_and_loads() -> None:
    assert DEFAULT_PHASE2_GATES_PATH.exists(), (
        f"Missing groundedness gates config: {DEFAULT_PHASE2_GATES_PATH}"
    )
    thresholds = load_phase2_gate_thresholds()
    data = thresholds.as_dict()
    assert data["unanswerable_accuracy_min"] >= 0.0
    assert data["grounding_contract_pass_rate_min"] >= 0.0
    assert data["citation_precision_eq"] >= 0.0
    assert data["known_bad_citations_count_eq"] >= 0
    assert data["valid_citation_rate_eq"] >= 0.0
    assert data["supported_rate_eq"] >= 0.0
    assert data["overclaim_rate_eq"] >= 0.0


def test_phase2_gates_invalid_json_raises_value_error(tmp_path) -> None:
    bad_path = tmp_path / "phase2_groundedness_gates.json"
    bad_path.write_text("{ not-valid-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_phase2_gate_thresholds(bad_path)
