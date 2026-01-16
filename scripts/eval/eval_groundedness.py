from __future__ import annotations

"""Groundedness-aware evaluation using the existing eval schema and RAG pipeline."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from api_clients.llm_client import LLMProviderError
from earCrawler.rag.pipeline import answer_with_rag


def _load_manifest(manifest_path: Path) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _resolve_dataset(manifest: dict, dataset_id: str, manifest_path: Path) -> Path:
    for entry in manifest.get("datasets", []):
        if entry.get("id") == dataset_id:
            file = Path(entry["file"])
            return file if file.is_absolute() else manifest_path.parent / file
    raise ValueError(f"Dataset not found: {dataset_id}")


def _iter_items(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def evaluate_groundedness(
    dataset_id: str,
    *,
    manifest_path: Path,
    llm_provider: str | None,
    llm_model: str | None,
    max_items: int | None,
    out_dir: Path,
) -> Path:
    manifest = _load_manifest(manifest_path)
    data_path = _resolve_dataset(manifest, dataset_id, manifest_path)

    results: List[Dict[str, Any]] = []
    total = 0
    grounded_hits = 0

    for idx, item in enumerate(_iter_items(data_path)):
        if max_items is not None and idx >= max_items:
            break
        question = item.get("question", "")
        task = str(item.get("task") or "").strip() or None
        ear_sections = item.get("ear_sections") or []
        try:
            rag_result = answer_with_rag(
                question,
                task=task,
                provider=llm_provider,
                model=llm_model,
                top_k=5,
            )
            used_sections = rag_result.get("used_sections") or []
            grounded = bool(set(ear_sections) & set(used_sections))
            grounded_hits += 1 if grounded else 0
            results.append(
                {
                    "id": item.get("id"),
                    "question": question,
                    "task": item.get("task"),
                    "answer": rag_result.get("answer"),
                    "used_sections": used_sections,
                    "raw_context": rag_result.get("raw_context"),
                    "expected_sections": ear_sections,
                    "grounded": grounded,
                    "evidence": item.get("evidence"),
                }
            )
        except LLMProviderError as exc:
            results.append(
                {
                    "id": item.get("id"),
                    "question": question,
                    "task": item.get("task"),
                    "error": str(exc),
                }
            )
        total += 1

    grounded_rate = grounded_hits / total if total else 0.0
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dataset_id}.groundedness.json"
    payload = {
        "dataset_id": dataset_id,
        "num_items": total,
        "grounded_rate": grounded_rate,
        "results": results,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate groundedness over existing eval datasets using the RAG pipeline."
    )
    parser.add_argument(
        "--dataset-id",
        required=True,
        help="Dataset ID from eval/manifest.json (e.g., ear_compliance.v1).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval") / "manifest.json",
        help="Path to eval manifest JSON.",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["nvidia_nim", "groq"],
        default=None,
        help="LLM provider override.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model override for the chosen provider.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional cap on number of items to evaluate.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("dist") / "eval",
        help="Output directory for groundedness metrics.",
    )
    args = parser.parse_args(argv)

    try:
        out_path = evaluate_groundedness(
            args.dataset_id,
            manifest_path=args.manifest,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            max_items=args.max_items,
            out_dir=args.out_dir,
        )
    except Exception as exc:  # pragma: no cover - surfaced as CLI failure
        print(f"Failed: {exc}")
        return 1
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
