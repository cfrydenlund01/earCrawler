from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import api_clients.llm_client as llm_client
from earCrawler.rag import pipeline
from earCrawler.rag.output_schema import make_unanswerable_payload
from scripts.eval import eval_rag_llm


def _extract_context_blocks(messages: Sequence[Mapping[str, object]]) -> list[str]:
    user_text = ""
    for msg in messages:
        if str(msg.get("role") or "") == "user":
            user_text = str(msg.get("content") or "")
            break
    if not user_text:
        return []

    start = user_text.find("Context:\n")
    end = user_text.rfind("\n\nQuestion:")
    if start < 0 or end < 0 or end <= start:
        return []
    blob = user_text[start + len("Context:\n") : end].strip()
    if not blob:
        return []
    return [b.strip() for b in blob.split("\n\n") if b.strip()]


def _extract_section_id_from_context_block(block: str) -> str | None:
    """Return the normalized section id from a '[SECTION] text' context block."""

    value = (block or "").strip()
    if not value.startswith("["):
        return None
    close = value.find("]")
    if close <= 1:
        return None
    raw_section = value[1:close].strip()
    return pipeline._normalize_section_id(raw_section) or None


def _stub_generate_chat(
    messages: list[dict[str, str]],
    provider: str | None = None,
    model: str | None = None,
    *,
    timeout: float | None = None,
) -> str:
    ctx_blocks = _extract_context_blocks(messages)
    citations: list[dict[str, str]] = []
    seen_sections: set[str] = set()

    for block in ctx_blocks:
        section_id = _extract_section_id_from_context_block(block)
        if not section_id or section_id in seen_sections:
            continue
        seen_sections.add(section_id)
        # Quote must be a verbatim substring of the provided context.
        quote = block[:220]
        citations.append({"section_id": section_id, "quote": quote, "span_id": ""})
        if len(citations) >= 3:
            break

    payload: dict[str, Any] = make_unanswerable_payload(
        hint="the relevant EAR section excerpt(s) for this scenario (for example: ECCN, destination, end user/end use)",
        justification="Stubbed offline LLM (no remote provider key configured).",
        evidence_reasons=["stub_llm_no_remote_key"],
    )
    payload["citations"] = citations
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run multihop ablation compare with a stubbed offline LLM (no remote keys required)."
    )
    parser.add_argument("--run-id", default="multihop_slice.v1.ablation_compare.stubbed")
    parser.add_argument("--dataset-id", default="multihop_slice.v1")
    parser.add_argument("--manifest", type=Path, default=Path("eval") / "manifest.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-items", type=int, default=None)
    args = parser.parse_args(argv)

    os.environ.setdefault("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    os.environ.setdefault("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    os.environ.setdefault("EARCRAWLER_KG_EXPANSION_PROVIDER", "json_stub")
    os.environ.setdefault(
        "EARCRAWLER_KG_EXPANSION_PATH", str((Path("data") / "kg_expansion.json").resolve())
    )

    orig_client = llm_client.generate_chat
    orig_pipeline = pipeline.generate_chat
    llm_client.generate_chat = _stub_generate_chat  # type: ignore[assignment]
    pipeline.generate_chat = _stub_generate_chat  # type: ignore[assignment]
    try:
        return eval_rag_llm.main(
            [
                "--dataset-id",
                str(args.dataset_id),
                "--manifest",
                str(args.manifest),
                "--top-k",
                str(int(args.top_k)),
                "--ablation-compare",
                "--ablation-run-id",
                str(args.run_id),
                "--multihop-only",
                *(["--max-items", str(int(args.max_items))] if args.max_items else []),
                # Avoid failing the run on trace-pack thresholds; this mode is about
                # validating KG/citation/grounding plumbing offline.
                "--trace-pack-threshold",
                "0.0",
            ]
        )
    finally:
        llm_client.generate_chat = orig_client  # type: ignore[assignment]
        pipeline.generate_chat = orig_pipeline  # type: ignore[assignment]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
