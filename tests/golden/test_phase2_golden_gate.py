from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Mapping

import pytest

import api_clients.llm_client as llm_client
from api_clients.llm_client import LLMProviderError
from earCrawler.eval.groundedness_gates import (
    evaluate_groundedness_signals,
    load_phase2_gate_thresholds,
)
from earCrawler.eval.provenance import (
    build_eval_provenance_snapshot,
    write_eval_provenance_snapshot,
)
from earCrawler.rag import pipeline
from tests.fixtures.golden_llm_outputs import GOLDEN_LLM_OUTPUTS
from tests.fixtures.golden_retrieval_map import GOLDEN_RETRIEVAL_MAP

try:
    from pytest_socket import disable_socket, enable_socket, socket_allow_hosts
except Exception:  # pragma: no cover - pytest_socket optional fallback
    disable_socket = enable_socket = socket_allow_hosts = None  # type: ignore[assignment]


DATASET_ID = "golden_phase2.v1"
DATASET_PATH = Path("eval") / f"{DATASET_ID}.jsonl"
FAILURE_MODE_DATASET_ID = "golden_phase2.failure_modes.v1"
FAILURE_MODE_DATASET_PATH = Path("eval") / f"{FAILURE_MODE_DATASET_ID}.jsonl"
RESERVED_OR_INVALID_SECTION_IDS = {"EAR-740.9(a)(2)"}
MULTI_CITATION_REQUIRED_IDS = {"gph2-ans-007", "gph2-ans-010", "gph2-ans-011"}
DEFAULT_CASE_ENV = {
    "EARCRAWLER_REMOTE_LLM_POLICY": "allow",
    "EARCRAWLER_ENABLE_REMOTE_LLM": "1",
    "EARCRAWLER_SKIP_LLM_SECRETS_FILE": "1",
    "EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL": "1",
    "EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE": "0.5",
}
OPTIONAL_CASE_ENV_KEYS = {
    "EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS",
    "EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS",
}
UNEXPECTED_LLM_CALL_SENTINEL = "__unexpected_llm_call__"


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
        or (
            (item.get("ground_truth") or {}).get("label")
            if isinstance(item.get("ground_truth"), Mapping)
            else ""
        )
        or "unknown"
    ).strip().lower()
    expected_citations = _normalize_set(
        (expected.get("citations") if isinstance(expected, Mapping) else None)
        or item.get("ear_sections")
        or []
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


def _fixture_quote_supported(*, item_id: str, section_id: str, quote: str) -> bool:
    quote = str(quote or "")
    if not quote.strip():
        return False
    for doc in GOLDEN_RETRIEVAL_MAP.get(item_id) or []:
        doc_section = pipeline._normalize_section_id(doc.get("section"))
        if doc_section != section_id:
            continue
        text = str(doc.get("text") or "")
        if quote in text:
            return True
    return False


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


def _render_failure_mode_rows(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"{title}: none"
    lines = [f"{title} ({len(rows)}):"]
    for row in rows:
        lines.append(
            " - "
            + (
                f"{row['id']} | outcome={row['expected_outcome']}"
                f" | gate={row['expected_gate']}"
                f" | expected_reasons={','.join(row['expected_reasons']) or 'none'}"
                f" | observed_reasons={','.join(row['failure_reasons']) or 'none'}"
                f" | output_error={row['output_error_code'] or 'none'}"
                f" | predicted={row['predicted_label'] or 'none'}"
                f" | llm_enabled={row['llm_enabled']}"
                f" | missing_hints={','.join(row['missing_hint_keywords']) or 'none'}"
            )
        )
    return "\n".join(lines)


def _write_optional_eval_artifacts(
    *,
    dataset_id: str,
    dataset_path: Path,
    thresholds: Mapping[str, object],
) -> Path | None:
    if not str(os.getenv("EARCRAWLER_WRITE_EVAL_ARTIFACTS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    run_id = f"{dataset_id}.golden_gate"
    index_meta_path = Path("data") / "faiss" / "index.meta.json"
    index_meta = json.loads(index_meta_path.read_text(encoding="utf-8"))
    return write_eval_provenance_snapshot(
        build_eval_provenance_snapshot(
            dataset_id=dataset_id,
            dataset_path=dataset_path,
            eval_suite=dataset_id,
            thresholds=thresholds,
            run_id=run_id,
            corpus_digest=str(index_meta.get("corpus_digest") or ""),
            index_meta_path=index_meta_path,
            top_k=5,
            strict_output=True,
            kg_expansion_enabled=False,
            llm_mode="stubbed",
            llm_provider="stubbed",
            llm_model="stubbed",
            remote_llm_enabled=True,
        ),
        artifact_root=Path("dist") / "eval" / run_id,
    )


def _regression_meta(item: Mapping[str, object]) -> Mapping[str, object]:
    regression = item.get("regression")
    return regression if isinstance(regression, Mapping) else {}


def _required_hint_keywords(item: Mapping[str, object]) -> list[str]:
    regression = _regression_meta(item)
    return [
        str(keyword).strip()
        for keyword in (regression.get("hint_keywords") or [])
        if str(keyword).strip()
    ]


def _apply_case_env(monkeypatch, item: Mapping[str, object]) -> None:
    for key in OPTIONAL_CASE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in DEFAULT_CASE_ENV.items():
        monkeypatch.setenv(key, value)

    regression = _regression_meta(item)
    env_overrides = regression.get("env") if isinstance(regression.get("env"), Mapping) else {}
    for key, value in env_overrides.items():
        monkeypatch.setenv(str(key), str(value))


def _assert_pack_fixture_coverage(items: list[dict], *, dataset_name: str) -> None:
    ids = {str(item["id"]) for item in items}
    missing_retrieval = sorted(ids - set(GOLDEN_RETRIEVAL_MAP))
    missing_outputs = sorted(ids - set(GOLDEN_LLM_OUTPUTS))
    assert not missing_retrieval, f"{dataset_name} missing retrieval fixtures: {missing_retrieval}"
    assert not missing_outputs, f"{dataset_name} missing LLM fixtures: {missing_outputs}"


def _install_offline_stubs(monkeypatch, active: dict[str, str | None]) -> None:
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
        if payload == UNEXPECTED_LLM_CALL_SENTINEL:
            raise AssertionError(f"generate_chat must not be called for {item_id}")
        if payload.startswith("__raise_llm_provider_error__:"):
            raise LLMProviderError(payload.split(":", 1)[1].strip())
        return payload

    monkeypatch.setattr(pipeline, "retrieve_regulation_context", _stub_retrieve)
    monkeypatch.setattr(pipeline, "expand_with_kg", lambda *_a, **_k: [])
    monkeypatch.setattr(llm_client, "generate_chat", _stub_generate_chat)
    monkeypatch.setattr(pipeline, "generate_chat", _stub_generate_chat)


def _raw_citations_from_result(result: Mapping[str, object]) -> list[dict[str, str]]:
    raw_answer = str(result.get("raw_answer") or "").strip()
    if not raw_answer:
        return []
    try:
        payload = json.loads(raw_answer)
    except json.JSONDecodeError:
        return []
    citations = payload.get("citations") if isinstance(payload, Mapping) else []
    rows: list[dict[str, str]] = []
    for citation in citations or []:
        if not isinstance(citation, Mapping):
            continue
        rows.append(
            {
                "section_id": str(citation.get("section_id") or ""),
                "quote": str(citation.get("quote") or ""),
            }
        )
    return rows


def _quote_matches_other_section(item_id: str, result: Mapping[str, object]) -> bool:
    for citation in _raw_citations_from_result(result):
        quote = citation["quote"]
        if not quote.strip():
            continue
        cited_section = pipeline._normalize_section_id(citation["section_id"])
        for doc in GOLDEN_RETRIEVAL_MAP.get(item_id) or []:
            doc_section = pipeline._normalize_section_id(doc.get("section"))
            if doc_section == cited_section:
                continue
            if quote in str(doc.get("text") or ""):
                return True
    return False


def _collect_failure_mode_reasons(
    *,
    item_id: str,
    item: Mapping[str, object],
    result: Mapping[str, object],
    groundedness_eval: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    reasons: set[str] = set()
    output_error = result.get("output_error") if isinstance(result.get("output_error"), Mapping) else {}
    output_error_code = str(output_error.get("code") or "").strip()

    if output_error_code == "invalid_section_id":
        reasons.add("invalid_section_id")
    elif output_error_code == "ungrounded_citation":
        reasons.add(
            "quote_section_mismatch"
            if _quote_matches_other_section(item_id, result)
            else "ungrounded_citation"
        )
    elif output_error_code:
        reasons.add(output_error_code)

    if "quote_not_in_section_context" in (groundedness_eval.get("errors") or []):
        reasons.add("quote_section_mismatch")
    if bool((groundedness_eval.get("overclaim") or {}).get("overclaim_count")):
        reasons.add("overclaim_nonzero")

    expected_label, _ = _extract_expected(item)
    predicted_label = str(result.get("label") or "").strip().lower()
    hint_keywords = _required_hint_keywords(item)
    answer_text = str(result.get("answer") or "")
    missing_hint_keywords = [
        keyword for keyword in hint_keywords if keyword.lower() not in answer_text.lower()
    ]

    if expected_label == "unanswerable":
        if predicted_label != "unanswerable":
            reasons.add("refusal_expected_missing")
        elif missing_hint_keywords:
            reasons.add("unanswerable_hint_missing")

    regression = _regression_meta(item)
    if bool(regression.get("must_skip_llm")):
        if bool(result.get("llm_enabled")):
            reasons.add("llm_called_despite_thin_retrieval")
        if str(result.get("disabled_reason") or "").strip() != "insufficient_evidence":
            reasons.add("thin_retrieval_refusal_missing")

    return sorted(reasons), missing_hint_keywords


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
    thresholds = load_phase2_gate_thresholds()
    assert DATASET_PATH.exists(), f"Missing dataset file: {DATASET_PATH}"
    items = _iter_jsonl(DATASET_PATH)
    assert 10 <= len(items) <= 20, "golden_phase2.v1 must contain 10-20 cases"
    _assert_pack_fixture_coverage(items, dataset_name=DATASET_ID)

    active: dict[str, str | None] = {"id": None}
    _install_offline_stubs(monkeypatch, active)

    infra_failures: list[dict] = []
    item_rows: list[dict] = []

    unanswerable_total = 0
    unanswerable_correct = 0
    grounding_total = 0
    grounding_pass = 0
    citation_tp_total = 0
    citation_pred_total = 0
    known_bad_citations_count = 0
    groundedness_counts = {
        "items_with_citations": 0,
        "total_citations": 0,
        "valid_citations": 0,
        "total_claims": 0,
        "supported_claims": 0,
        "overclaim_count": 0,
        "items_overclaim": 0,
    }

    for item in items:
        item_id = str(item["id"])
        active["id"] = item_id
        _apply_case_env(monkeypatch, item)
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
        groundedness_eval = evaluate_groundedness_signals(result)
        for key, value in groundedness_eval["counts"].items():
            groundedness_counts[key] = groundedness_counts.get(key, 0) + int(value)

        quote_conditions: list[str] = []
        for citation in result.get("citations") or []:
            if not isinstance(citation, Mapping):
                continue
            cited_sec = pipeline._normalize_section_id(citation.get("section_id"))
            if not cited_sec:
                quote_conditions.append("quote:invalid_section_id")
                continue
            quote = str(citation.get("quote") or "")
            if not quote.strip():
                quote_conditions.append("quote:missing")
                continue
            if not _fixture_quote_supported(item_id=item_id, section_id=cited_sec, quote=quote):
                quote_conditions.append("quote:not_substring_of_fixture_text")

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
        grounding_conditions.extend(quote_conditions)

        if item_id in MULTI_CITATION_REQUIRED_IDS:
            if len(expected_citations) < 2:
                grounding_conditions.append("multi:expected_lt2")
            if predicted_citations != expected_citations:
                grounding_conditions.append("multi:predicted_not_exact_expected")

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
                "groundedness_errors": groundedness_eval["errors"],
                "overclaim_snippets": groundedness_eval["overclaim"]["snippets"],
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
    valid_citation_rate = (
        groundedness_counts["valid_citations"] / groundedness_counts["total_citations"]
        if groundedness_counts["total_citations"]
        else 1.0
    )
    supported_rate = (
        groundedness_counts["supported_claims"] / groundedness_counts["total_claims"]
        if groundedness_counts["total_claims"]
        else 1.0
    )
    overclaim_rate = (
        groundedness_counts["overclaim_count"] / groundedness_counts["total_claims"]
        if groundedness_counts["total_claims"]
        else 0.0
    )

    bad_unanswerable_rows = [
        row
        for row in item_rows
        if row["expected_label"] == "unanswerable" and row["predicted_label"] != "unanswerable"
    ]
    bad_grounding_rows = [
        row
        for row in item_rows
        if "grounding" in row["failure_types"] or "schema" in row["failure_types"]
    ]
    bad_citation_rows = [row for row in item_rows if row["known_bad"]]
    bad_support_rows = [
        row
        for row in item_rows
        if row["groundedness_errors"] or row["overclaim_snippets"]
    ]
    _write_optional_eval_artifacts(
        dataset_id=DATASET_ID,
        dataset_path=DATASET_PATH,
        thresholds=thresholds.as_dict(),
    )

    infra_block = (
        "infra_failures: none"
        if not infra_failures
        else "infra_failures:\n"
        + "\n".join(f" - {row['id']}: {row['error']}" for row in infra_failures)
    )

    assert unanswerable_accuracy >= thresholds.unanswerable_accuracy_min, (
        f"Phase 2 gate failed: unanswerable_accuracy={unanswerable_accuracy:.4f} < "
        f"{thresholds.unanswerable_accuracy_min:.4f}\n"
        f"Formula: correct_unanswerable / total_unanswerable = {unanswerable_correct}/{unanswerable_total}\n"
        f"{_render_rows('Unanswerable failures', bad_unanswerable_rows)}\n"
        f"{infra_block}"
    )
    assert grounding_contract_pass_rate >= thresholds.grounding_contract_pass_rate_min, (
        f"Phase 2 gate failed: grounding_contract_pass_rate={grounding_contract_pass_rate:.4f} < "
        f"{thresholds.grounding_contract_pass_rate_min:.4f}\n"
        f"Formula: grounding_passes / total_items_scored = {grounding_pass}/{grounding_total}\n"
        f"{_render_rows('Grounding/schema failures', bad_grounding_rows)}\n"
        f"{infra_block}"
    )
    assert citation_precision == thresholds.citation_precision_eq, (
        f"Phase 2 gate failed: citation_precision={citation_precision:.4f} != "
        f"{thresholds.citation_precision_eq:.4f}\n"
        f"Formula: sum(|predicted ∩ expected|) / sum(|predicted|) = {citation_tp_total}/{citation_pred_total}\n"
        f"{_render_rows('Citation failures', bad_citation_rows)}\n"
        f"{infra_block}"
    )
    assert known_bad_citations_count == thresholds.known_bad_citations_count_eq, (
        f"Phase 2 gate failed: known_bad_citations_count={known_bad_citations_count} != "
        f"{thresholds.known_bad_citations_count_eq}\n"
        f"Known-bad means cited section not in expected set or reserved/invalid cited.\n"
        f"{_render_rows('Known-bad citation rows', bad_citation_rows)}\n"
        f"{infra_block}"
    )
    assert valid_citation_rate == thresholds.valid_citation_rate_eq, (
        f"Phase 2 gate failed: valid_citation_rate={valid_citation_rate:.4f} != "
        f"{thresholds.valid_citation_rate_eq:.4f}\n"
        f"Formula: valid_citations / total_citations = "
        f"{groundedness_counts['valid_citations']}/{groundedness_counts['total_citations']}\n"
        f"{_render_rows('Validity/support failures', bad_support_rows)}\n"
        f"{infra_block}"
    )
    assert supported_rate == thresholds.supported_rate_eq, (
        f"Phase 2 gate failed: supported_rate={supported_rate:.4f} != "
        f"{thresholds.supported_rate_eq:.4f}\n"
        f"Formula: supported_claims / total_decisive_claims = "
        f"{groundedness_counts['supported_claims']}/{groundedness_counts['total_claims']}\n"
        f"{_render_rows('Validity/support failures', bad_support_rows)}\n"
        f"{infra_block}"
    )
    assert overclaim_rate == thresholds.overclaim_rate_eq, (
        f"Phase 2 gate failed: overclaim_rate={overclaim_rate:.4f} != "
        f"{thresholds.overclaim_rate_eq:.4f}\n"
        f"Formula: overclaim_count / total_decisive_claims = "
        f"{groundedness_counts['overclaim_count']}/{groundedness_counts['total_claims']}\n"
        f"{_render_rows('Overclaim failures', bad_support_rows)}\n"
        f"{infra_block}"
    )


def test_phase2_failure_mode_pack(monkeypatch) -> None:
    assert FAILURE_MODE_DATASET_PATH.exists(), f"Missing dataset file: {FAILURE_MODE_DATASET_PATH}"
    items = _iter_jsonl(FAILURE_MODE_DATASET_PATH)
    assert len(items) == 9, "golden_phase2.failure_modes.v1 must contain 9 cases"
    _assert_pack_fixture_coverage(items, dataset_name=FAILURE_MODE_DATASET_ID)

    active: dict[str, str | None] = {"id": None}
    _install_offline_stubs(monkeypatch, active)

    pass_rows: list[dict] = []
    fail_rows: list[dict] = []

    for item in items:
        item_id = str(item["id"])
        active["id"] = item_id
        _apply_case_env(monkeypatch, item)
        regression = _regression_meta(item)
        expected_outcome = str(regression.get("expected_outcome") or "").strip().lower()
        expected_gate = str(regression.get("expected_gate") or "").strip()
        expected_reasons = [
            str(reason).strip()
            for reason in (regression.get("expected_reasons") or [])
            if str(reason).strip()
        ]

        result = pipeline.answer_with_rag(
            str(item.get("question") or ""),
            task=str(item.get("task") or "") or None,
            strict_retrieval=False,
            strict_output=True,
            top_k=5,
        )

        groundedness_eval = evaluate_groundedness_signals(result)
        failure_reasons, missing_hint_keywords = _collect_failure_mode_reasons(
            item_id=item_id,
            item=item,
            result=result,
            groundedness_eval=groundedness_eval,
        )
        row = {
            "id": item_id,
            "expected_outcome": expected_outcome,
            "expected_gate": expected_gate,
            "expected_reasons": expected_reasons,
            "failure_reasons": failure_reasons,
            "missing_hint_keywords": missing_hint_keywords,
            "predicted_label": str(result.get("label") or "").strip().lower(),
            "output_error_code": (
                str((result.get("output_error") or {}).get("code") or "").strip() or None
            ),
            "llm_enabled": bool(result.get("llm_enabled")),
            "disabled_reason": str(result.get("disabled_reason") or "").strip() or None,
            "groundedness_errors": groundedness_eval["errors"],
        }

        if expected_outcome == "pass":
            pass_rows.append(row)
        elif expected_outcome == "fail":
            fail_rows.append(row)
        else:
            raise AssertionError(f"{item_id} has invalid expected_outcome: {expected_outcome}")

    bad_pass_rows = [row for row in pass_rows if row["failure_reasons"]]
    bad_fail_rows = [
        row
        for row in fail_rows
        if not set(row["expected_reasons"]).issubset(set(row["failure_reasons"]))
    ]

    assert not bad_pass_rows, (
        "Phase 2 failure-mode pack had expected-pass cases rejected.\n"
        f"{_render_failure_mode_rows('Expected-pass regressions', bad_pass_rows)}"
    )
    assert not bad_fail_rows, (
        "Phase 2 failure-mode pack missed expected adversarial failures.\n"
        f"{_render_failure_mode_rows('Expected-fail regressions', bad_fail_rows)}"
    )
