from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import api_clients.llm_client as llm_client
from api_clients.llm_client import LLMProviderError
from earCrawler.eval import citation_metrics
from earCrawler.rag import pipeline
from earCrawler.trace.trace_pack import validate_trace_pack
from scripts.eval import eval_rag_llm
from tests.fixtures.golden_llm_outputs import GOLDEN_LLM_OUTPUTS
from tests.fixtures.golden_retrieval_map import GOLDEN_RETRIEVAL_MAP


DATASET_ID_DEFAULT = "golden_phase2.v1"
RESERVED_OR_INVALID_SECTION_IDS = {"EAR-740.9(a)(2)"}
MULTI_CITATION_REQUIRED_IDS = {"gph2-ans-007", "gph2-ans-010", "gph2-ans-011"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def _normalize_set(values: Sequence[object]) -> set[str]:
    out: set[str] = set()
    for value in values:
        norm = pipeline._normalize_section_id(value)
        if norm:
            out.add(norm)
    return out


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


def _load_index_provenance(index_meta_path: Path) -> dict[str, object]:
    if not index_meta_path.exists():
        return {"meta_path": str(index_meta_path), "exists": False}
    try:
        meta = json.loads(index_meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"meta_path": str(index_meta_path), "exists": True, "error": str(exc)}
    return {
        "meta_path": str(index_meta_path),
        "exists": True,
        "schema_version": meta.get("schema_version"),
        "build_timestamp_utc": meta.get("build_timestamp_utc"),
        "corpus_digest": meta.get("corpus_digest"),
        "corpus_schema_version": meta.get("corpus_schema_version"),
        "doc_count": meta.get("doc_count"),
        "embedding_model": meta.get("embedding_model"),
        "snapshot": meta.get("snapshot") if isinstance(meta.get("snapshot"), Mapping) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline deterministic eval for golden_phase2.v1 using stubbed retrieval + LLM fixtures."
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=Path("eval") / f"{DATASET_ID_DEFAULT}.jsonl",
        help="Path to the golden phase2 dataset JSONL.",
    )
    parser.add_argument("--dataset-id", default=DATASET_ID_DEFAULT, help="Dataset id label for outputs.")
    parser.add_argument("--top-k", type=int, default=5, help="Top-k to feed to stub retriever.")
    parser.add_argument("--max-items", type=int, default=None, help="Optional cap on evaluated items.")
    parser.add_argument(
        "--index-meta",
        type=Path,
        default=Path("data") / "faiss" / "index.meta.json",
        help="Index metadata path for provenance (no retrieval performed).",
    )
    parser.add_argument("--run-id", default=None, help="Run id used for trace pack output folders.")
    parser.add_argument("--out-json", type=Path, required=True, help="Where to write metrics JSON.")
    parser.add_argument("--out-md", type=Path, default=None, help="Where to write markdown summary.")
    args = parser.parse_args(argv)

    if not args.dataset_path.exists():
        print(f"Failed: missing dataset file: {args.dataset_path}")
        return 1

    # Allow the pipeline to run even though we stub LLM calls (no secrets required).
    os.environ["EARCRAWLER_REMOTE_LLM_POLICY"] = "allow"
    os.environ["EARCRAWLER_ENABLE_REMOTE_LLM"] = "1"
    os.environ["EARCRAWLER_SKIP_LLM_SECRETS_FILE"] = "1"
    os.environ["EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL"] = "1"
    os.environ["EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE"] = "0.5"

    items = _iter_jsonl(args.dataset_path)
    if args.max_items is not None:
        items = items[: int(args.max_items)]
    item_ids = [str(item.get("id") or "") for item in items]
    if any(not item_id for item_id in item_ids):
        print("Failed: dataset contains item(s) with missing id")
        return 1

    missing_fixture = sorted(
        item_id
        for item_id in set(item_ids)
        if item_id not in GOLDEN_RETRIEVAL_MAP or item_id not in GOLDEN_LLM_OUTPUTS
    )
    if missing_fixture:
        print(f"Failed: missing fixture entries for {len(missing_fixture)} item(s): {missing_fixture[:5]}")
        return 1

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

    orig_retrieve = pipeline.retrieve_regulation_context
    orig_expand = pipeline.expand_with_kg
    orig_llm_client = llm_client.generate_chat
    orig_pipeline_chat = pipeline.generate_chat

    run_id = eval_rag_llm._safe_name(args.run_id or f"{args.dataset_id}.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    run_provenance = {
        "dataset_id": str(args.dataset_id),
        "timestamp": _utc_now_iso(),
        "index": _load_index_provenance(args.index_meta),
    }

    results: list[dict[str, object]] = []
    trace_packs: dict[str, dict[str, object]] = {}
    trace_pack_issues_by_item: dict[str, list[dict[str, str]]] = {}
    infra_failures: list[dict[str, str]] = []

    grounded_pass = 0
    grounding_total = 0
    tp_total = fp_total = fn_total = 0

    try:
        pipeline.retrieve_regulation_context = _stub_retrieve  # type: ignore[assignment]
        pipeline.expand_with_kg = lambda *_a, **_k: []  # type: ignore[assignment]
        llm_client.generate_chat = _stub_generate_chat  # type: ignore[assignment]
        pipeline.generate_chat = _stub_generate_chat  # type: ignore[assignment]

        for item in items:
            item_id = str(item.get("id") or "")
            active["id"] = item_id
            question = str(item.get("question") or "")
            task = str(item.get("task") or "") or None

            try:
                result = pipeline.answer_with_rag(
                    question,
                    task=task,
                    strict_retrieval=False,
                    strict_output=True,
                    top_k=int(args.top_k),
                )
            except LLMProviderError as exc:
                infra_failures.append({"id": item_id, "error": str(exc)})
                continue

            expected_label, expected_citations = _extract_expected(item)
            predicted_label = str(result.get("label") or "").strip().lower()
            predicted_citations = _extract_predicted(result)

            score = citation_metrics.score_citations(predicted_citations, expected_citations)
            tp_total += score.tp
            fp_total += score.fp
            fn_total += score.fn

            used_sections = _normalize_set(result.get("used_sections") or [])

            schema_valid = bool(result.get("output_ok"))
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

            grounding_total += 1
            grounding_conditions: list[str] = []
            if not schema_valid:
                grounding_conditions.append("schema")
            if expected_label != "unanswerable" and not predicted_citations:
                grounding_conditions.append("grounding:no_citations_for_answerable")
            if not predicted_citations.issubset(used_sections):
                grounding_conditions.append("grounding:citation_not_in_retrieval")
            grounding_conditions.extend(quote_conditions)

            if item_id in MULTI_CITATION_REQUIRED_IDS and predicted_citations != expected_citations:
                grounding_conditions.append("multi:predicted_not_exact_expected")

            known_bad = sorted(
                sec
                for sec in predicted_citations
                if sec in RESERVED_OR_INVALID_SECTION_IDS or sec not in expected_citations
            )
            if known_bad:
                grounding_conditions.append("citation:known_bad")

            grounded = len(grounding_conditions) == 0
            if grounded:
                grounded_pass += 1

            trace_id = str(result.get("trace_id") or f"{run_id}:{item_id}")
            trace_pack = eval_rag_llm._build_trace_pack(
                trace_id=trace_id,
                question=question,
                answer_text=str(result.get("answer") or ""),
                label=str(result.get("label") or ""),
                citations=result.get("citations") or [],
                retrieved_docs=result.get("retrieved_docs") or [],
                kg_paths_used=result.get("kg_paths_used") or [],
                run_provenance=run_provenance,
            )
            issues = validate_trace_pack(trace_pack, require_kg_paths=False)
            trace_packs[item_id] = trace_pack
            trace_pack_issues_by_item[item_id] = [issue.to_dict() for issue in issues]

            results.append(
                {
                    "id": item_id,
                    "task": task,
                    "question": question,
                    "expected_label": expected_label,
                    "predicted_label": predicted_label,
                    "answer_text": str(result.get("answer") or ""),
                    "citations": result.get("citations") or [],
                    "used_sections": sorted(used_sections),
                    "output_ok": bool(result.get("output_ok")),
                    "grounded": grounded,
                    "grounding_conditions": grounding_conditions,
                    "citation_precision": score.precision,
                    "citation_recall": score.recall,
                    "citation_tp": score.tp,
                    "citation_fp": score.fp,
                    "citation_fn": score.fn,
                    "trace_id": trace_id,
                    "provenance_hash": trace_pack.get("provenance_hash"),
                    "trace_pack_pass": len(issues) == 0,
                    "trace_pack_issues": trace_pack_issues_by_item[item_id],
                }
            )
    finally:
        pipeline.retrieve_regulation_context = orig_retrieve  # type: ignore[assignment]
        pipeline.expand_with_kg = orig_expand  # type: ignore[assignment]
        llm_client.generate_chat = orig_llm_client  # type: ignore[assignment]
        pipeline.generate_chat = orig_pipeline_chat  # type: ignore[assignment]

    num_items = len(results)
    grounded_rate = grounded_pass / grounding_total if grounding_total else 0.0
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else (1.0 if (tp_total + fp_total + fn_total) == 0 else 0.0)
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 1.0
    denom = precision + recall
    f1 = (2 * precision * recall / denom) if denom else (1.0 if (tp_total + fp_total + fn_total) == 0 else 0.0)

    trace_paths = eval_rag_llm._write_trace_pack_artifacts(
        trace_packs,
        dataset_id=str(args.dataset_id),
        run_id=run_id,
        base_dir=args.out_json.parent,
    )
    for row in results:
        item_id = str(row.get("id") or "")
        if item_id in trace_paths:
            row["trace_pack_path"] = str(trace_paths[item_id])

    trace_pack_pass_count = sum(1 for row in results if bool(row.get("trace_pack_pass")))
    trace_pack_pass_rate = trace_pack_pass_count / num_items if num_items else 0.0

    payload = {
        "dataset_id": str(args.dataset_id),
        "dataset_path": str(args.dataset_path),
        "run_id": run_id,
        "timestamp": _utc_now_iso(),
        "top_k": int(args.top_k),
        "num_items": num_items,
        "infra_failures": infra_failures,
        "grounded_rate": grounded_rate,
        "citation_pr": {
            "micro": {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "tp": tp_total,
                "fp": fp_total,
                "fn": fn_total,
            }
        },
        "trace_pack_metrics": {
            "num_items": num_items,
            "pass_count": trace_pack_pass_count,
            "pass_rate": trace_pack_pass_rate,
            "issues_by_item": trace_pack_issues_by_item,
        },
        "run_provenance": run_provenance,
        "results": results,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md = args.out_md or args.out_json.with_suffix(".md")
    lines = [
        f"# Offline golden eval: {args.dataset_id}",
        "",
        f"- Run id: `{run_id}`",
        f"- Timestamp (UTC): `{payload['timestamp']}`",
        f"- Items: `{num_items}` (top_k=`{args.top_k}`)",
        f"- Grounded rate: `{grounded_rate:.4f}`",
        f"- Citation micro P/R/F1: `{precision:.4f}` / `{recall:.4f}` / `{f1:.4f}`",
        f"- Trace packs: pass_rate=`{trace_pack_pass_rate:.4f}` ({trace_pack_pass_count}/{num_items})",
        "",
        "Artifacts:",
        f"- `{args.out_json.name}`",
        f"- `{out_md.name}`",
        f"- `{run_id}/trace_packs/{args.dataset_id}/`",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
