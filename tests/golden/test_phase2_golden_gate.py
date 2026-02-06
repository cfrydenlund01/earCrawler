from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

import pytest

import api_clients.llm_client as llm_client
from api_clients.llm_client import LLMProviderError
from earCrawler.rag import pipeline
from tests.fixtures.golden_llm_outputs import GOLDEN_LLM_OUTPUTS
from tests.fixtures.golden_retrieval_map import GOLDEN_RETRIEVAL_MAP

try:
    from pytest_socket import disable_socket, enable_socket, socket_allow_hosts
except Exception:  # pragma: no cover - pytest_socket optional fallback
    disable_socket = enable_socket = socket_allow_hosts = None  # type: ignore[assignment]


DATASET_ID = "golden_phase2.v1"
DATASET_PATH = Path("eval") / f"{DATASET_ID}.jsonl"
RESERVED_OR_INVALID_SECTION_IDS = {"EAR-740.9(a)(2)"}


def _iter_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _normalize_set(values: Iterable[object]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        norm = pipeline._normalize_section_id(value)
        if norm:
            normalized.add(norm)
    return normalized


def _extract_expected(item: Mapping[str, object]) -> tuple[str, set[str]]:
    expected = item.get("expected") if isinstance(item.get("expected"), Mapping) else {}
    expected_label = str(
        expected.get("label")
        or ((item.get("ground_truth") or {}).get("label") if isinstance(item.get("ground_truth"), Mapping) else "")
        or "unknown"
    ).strip().lower()
    expected_citations = _normalize_set(
        (expected.get("citations") if isinstance(expected, Mapping) else None) or item.get("ear_sections") or []
    )
    return expected_label, expected_citations


def _extract_predicted(result: Mapping[str, object]) -> set[str]:
    sections: set[str] = set()
    for citation in result.get("citations") or []:
        if not isinstance(citation, Mapping):
            continue
        norm = pipeline._normalize_section_id(citation.get("section_id"))
        if norm:
            sections.add(norm)
    return sections


def _render_rows(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"{title}: none"
    lines = [f"{title} ({len(rows)}):"]
    for row in rows:
        lines.append(
            " - "
            + (
                f"{row['id']} | type={','.join(row['failure_types']) or 'none'}"
                f" | expected={row['expected_label']}"
                f" | predicted={row['predicted_label']}"
                f" | expected_citations={row['expected_citations']}"
                f" | predicted_citations={row['predicted_citations']}"
                f" | retrieved_sections={row['retrieved_sections']}"
            )
        )
    return "\n".join(lines)


@pytest.fixture(autouse=True)
def _force_no_network():
    if not (disable_socket and enable_socket):
        yield
        return
    if socket_allow_hosts:
        socket_allow_hosts(["127.0.0.1", "::1"])
    disable_socket()
    try:
        yield
    finally:
        enable_socket()


def test_phase2_golden_gate(monkeypatch) -> None:
    assert DATASET_PATH.exists(), f"Missing dataset file: {DATASET_PATH}"
    items = _iter_jsonl(DATASET_PATH)
    assert 10 <= len(items) <= 20, "golden_phase2.v1 must contain 10-20 cases"
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")

    ids = {str(item["id"]) for item in items}
    assert ids == set(GOLDEN_RETRIEVAL_MAP), "Retrieval fixture keys must match golden item ids"
    assert ids == set(GOLDEN_LLM_OUTPUTS), "LLM fixture keys must match golden item ids"

    active: dict[str, str | None] = {"id": None}

    def _stub_retrieve(_query: str, top_k: int = 5, **_kwargs) -> list[dict]:
        item_id = active["id"]
        assert item_id is not None, "active item id not set"
        docs = GOLDEN_RETRIEVAL_MAP[item_id][:top_k]
        output: list[dict] = []
        for doc in docs:
            section = pipeline._normalize_section_id(doc.get("section"))
            output.append(
                {
                    "section_id": section,
                    "text": str(doc.get("text") or ""),
                    "score": doc.get("score"),
                    "raw": {
                        "id": section,
                        "section": section,
                        "title": doc.get("title"),
                        "source_url": doc.get("source_url"),
                    },
                }
            )
        return output

    def _stub_generate_chat(_messages, *_, **__) -> str:
        item_id = active["id"]
        assert item_id is not None, "active item id not set"
        payload = GOLDEN_LLM_OUTPUTS[item_id]
        if payload.startswith("__raise_llm_provider_error__:"):
            raise LLMProviderError(payload.split(":", 1)[1].strip())
        return payload

    monkeypatch.setattr(pipeline, "retrieve_regulation_context", _stub_retrieve)
    monkeypatch.setattr(pipeline, "expand_with_kg", lambda *_a, **_k: [])
    monkeypatch.setattr(llm_client, "generate_chat", _stub_generate_chat)
    monkeypatch.setattr(pipeline, "generate_chat", _stub_generate_chat)

    infra_failures: list[dict] = []
    item_rows: list[dict] = []

    unanswerable_total = 0
    unanswerable_correct = 0
    grounding_total = 0
    grounding_pass = 0
    citation_tp_total = 0
    citation_pred_total = 0
    known_bad_citations_count = 0

    for item in items:
        item_id = str(item["id"])
        active["id"] = item_id
        expected_label, expected_citations = _extract_expected(item)
        try:
            result = pipeline.answer_with_rag(
                str(item.get("question") or ""),
                task=str(item.get("task") or "") or None,
                strict_retrieval=False,
                strict_output=True,
                top_k=5,
            )
        except LLMProviderError as exc:
            infra_failures.append({"id": item_id, "error": str(exc)})
            continue

        predicted_label = str(result.get("label") or "").strip().lower()
        predicted_citations = _extract_predicted(result)
        retrieved_sections = _normalize_set(result.get("used_sections") or [])
        schema_valid = bool(result.get("output_ok"))

        if expected_label == "unanswerable":
            unanswerable_total += 1
            if predicted_label == "unanswerable":
                unanswerable_correct += 1

        grounding_total += 1
        grounding_conditions: list[str] = []
        if not schema_valid:
            grounding_conditions.append("schema")
        if expected_label != "unanswerable" and not predicted_citations:
            grounding_conditions.append("grounding:no_citations_for_answerable")
        if not predicted_citations.issubset(retrieved_sections):
            grounding_conditions.append("grounding:citation_not_in_retrieval")

        grounding_item_pass = len(grounding_conditions) == 0
        if grounding_item_pass:
            grounding_pass += 1

        citation_tp_total += len(predicted_citations & expected_citations)
        citation_pred_total += len(predicted_citations)

        known_bad = sorted(
            sec
            for sec in predicted_citations
            if sec in RESERVED_OR_INVALID_SECTION_IDS or sec not in expected_citations
        )
        known_bad_citations_count += len(known_bad)

        failure_types: list[str] = []
        if not schema_valid:
            failure_types.append("schema")
        if not grounding_item_pass:
            failure_types.append("grounding")
        if known_bad:
            failure_types.append("citation")

        item_rows.append(
            {
                "id": item_id,
                "expected_label": expected_label,
                "predicted_label": predicted_label,
                "expected_citations": sorted(expected_citations),
                "predicted_citations": sorted(predicted_citations),
                "retrieved_sections": sorted(retrieved_sections),
                "failure_types": failure_types,
                "known_bad": known_bad,
            }
        )

    scored_items = len(item_rows)
    assert scored_items > 0, "No scored items available for golden gate metrics"

    unanswerable_accuracy = (
        unanswerable_correct / unanswerable_total if unanswerable_total else 1.0
    )
    grounding_contract_pass_rate = grounding_pass / grounding_total if grounding_total else 0.0
    citation_precision = (
        citation_tp_total / citation_pred_total if citation_pred_total else 1.0
    )

    bad_unanswerable_rows = [
        row
        for row in item_rows
        if row["expected_label"] == "unanswerable" and row["predicted_label"] != "unanswerable"
    ]
    bad_grounding_rows = [row for row in item_rows if "grounding" in row["failure_types"] or "schema" in row["failure_types"]]
    bad_citation_rows = [row for row in item_rows if row["known_bad"]]

    infra_block = (
        "infra_failures: none"
        if not infra_failures
        else "infra_failures:\n" + "\n".join(f" - {row['id']}: {row['error']}" for row in infra_failures)
    )

    assert unanswerable_accuracy >= 0.9, (
        f"Phase 2 gate failed: unanswerable_accuracy={unanswerable_accuracy:.4f} < 0.9\n"
        f"Formula: correct_unanswerable / total_unanswerable = {unanswerable_correct}/{unanswerable_total}\n"
        f"{_render_rows('Unanswerable failures', bad_unanswerable_rows)}\n"
        f"{infra_block}"
    )
    assert grounding_contract_pass_rate >= 0.8, (
        f"Phase 2 gate failed: grounding_contract_pass_rate={grounding_contract_pass_rate:.4f} < 0.8\n"
        f"Formula: grounding_passes / total_items_scored = {grounding_pass}/{grounding_total}\n"
        f"{_render_rows('Grounding/schema failures', bad_grounding_rows)}\n"
        f"{infra_block}"
    )
    assert citation_precision == 1.0, (
        f"Phase 2 gate failed: citation_precision={citation_precision:.4f} != 1.0\n"
        f"Formula: sum(|predicted ∩ expected|) / sum(|predicted|) = {citation_tp_total}/{citation_pred_total}\n"
        f"{_render_rows('Citation failures', bad_citation_rows)}\n"
        f"{infra_block}"
    )
    assert known_bad_citations_count == 0, (
        f"Phase 2 gate failed: known_bad_citations_count={known_bad_citations_count} != 0\n"
        f"Known-bad means cited section not in expected set or reserved/invalid cited.\n"
        f"{_render_rows('Known-bad citation rows', bad_citation_rows)}\n"
        f"{infra_block}"
    )
