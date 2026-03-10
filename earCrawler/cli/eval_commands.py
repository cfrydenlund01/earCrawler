from __future__ import annotations

"""Evaluation CLI command group and registrar."""

import json
from pathlib import Path

import click

from earCrawler.security import policy


def _iter_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                items.append(json.loads(stripped))
    return items


@click.group(name="eval")
@policy.require_role("operator", "maintainer")
@policy.enforce
def eval_group() -> None:
    """Evaluation utilities."""


@eval_group.command(name="verify-evidence")
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("eval") / "manifest.json",
    show_default=True,
    help="Eval manifest describing dataset files.",
)
@click.option(
    "--corpus",
    type=click.Path(path_type=Path),
    default=Path("data") / "fr_sections.jsonl",
    show_default=True,
    help="Corpus JSONL to validate references against.",
)
@click.option(
    "--dataset-id",
    default="all",
    show_default=True,
    help="Dataset id to verify, or 'all' for every entry in the manifest.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval" / "evidence_report.json",
    show_default=True,
    help="Where to write the evidence resolution report.",
)
def eval_verify_evidence(
    manifest: Path, corpus: Path, dataset_id: str, out: Path
) -> None:
    """Gate eval datasets by verifying evidence <-> corpus alignment."""

    try:
        manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - manifest parsing errors
        raise click.ClickException(f"Failed to read manifest: {exc}")

    dataset_entries = manifest_obj.get("datasets", [])
    if dataset_id != "all":
        dataset_entries = [
            entry for entry in dataset_entries if entry.get("id") == dataset_id
        ]
        if not dataset_entries:
            raise click.ClickException(f"Dataset not found: {dataset_id}")

    try:
        from earCrawler.eval.evidence_resolver import load_corpus_index, resolve_dataset
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    try:
        corpus_index = load_corpus_index(corpus)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc))
    report: dict[str, object] = {
        "corpus_path": str(corpus),
        "datasets": [],
    }
    missing_sections: set[str] = set()
    missing_spans: set[str] = set()

    for entry in dataset_entries:
        ds_id = entry.get("id")
        raw_file = entry.get("file")
        if not raw_file:
            raise click.ClickException(f"Dataset entry missing file: {ds_id}")
        data_file = Path(str(raw_file))
        if not data_file.is_absolute() and not data_file.exists():
            data_file = manifest.parent / data_file
        if not data_file.exists():
            raise click.ClickException(f"Dataset not found: {data_file}")
        items = _iter_jsonl(data_file)
        ds_report = resolve_dataset(ds_id, items, corpus_index)
        ds_report["file"] = str(data_file)
        report["datasets"].append(ds_report)
        missing_sections.update(ds_report["missing_sections"])
        missing_spans.update(ds_report["missing_spans"])
        click.echo(
            f"{ds_id}: missing_sections={len(ds_report['missing_sections'])}, "
            f"missing_spans={len(ds_report['missing_spans'])}"
        )

    report["summary"] = {
        "missing_sections": sorted(missing_sections),
        "missing_spans": sorted(missing_spans),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if missing_sections or missing_spans:
        raise click.ClickException("evidence verification failed")


@eval_group.command(name="build-kg-expansion")
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("eval") / "manifest.json",
    show_default=True,
    help="Eval manifest to harvest referenced sections and KG hints.",
)
@click.option(
    "--corpus",
    type=click.Path(path_type=Path),
    default=Path("data") / "fr_sections.jsonl",
    show_default=True,
    help="Corpus JSONL containing section text.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("data") / "kg_expansion.json",
    show_default=True,
    help="Destination JSON file for KG expansion mapping.",
)
def build_kg_expansion(manifest: Path, corpus: Path, out: Path) -> None:
    """Generate the file-backed KG expansion mapping."""

    try:
        from earCrawler.rag.kg_expansion_builder import (
            build_expansion_mapping,
            write_expansion_mapping,
        )
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))
    mapping = build_expansion_mapping(corpus, manifest)
    write_expansion_mapping(out, mapping)
    click.echo(f"Wrote {out} ({len(mapping)} sections)")


@eval_group.command(name="run-rag")
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("eval") / "manifest.json",
    show_default=True,
    help="Eval manifest describing datasets and KG state.",
)
@click.option(
    "--dataset-id",
    default=None,
    help="Optional dataset id to run; defaults to all entries in the manifest.",
)
@click.option(
    "--provider",
    default="groq",
    show_default=True,
    help="LLM provider override (defaults to Groq).",
)
@click.option(
    "--model",
    default="llama-3.3-70b-versatile",
    show_default=True,
    help="LLM model identifier for the provider.",
)
@click.option(
    "--top-k",
    type=int,
    default=5,
    show_default=True,
    help="Number of contexts to retrieve before generation.",
)
@click.option(
    "--retrieval-mode",
    type=click.Choice(["dense", "hybrid"]),
    default=None,
    help="Retrieval mode override: dense (default) or hybrid BM25+dense fusion.",
)
@click.option(
    "--compare-retrieval-modes/--no-compare-retrieval-modes",
    default=False,
    show_default=True,
    help="Run dense and hybrid retrieval side by side and write a comparison summary.",
)
@click.option(
    "--max-items",
    type=int,
    default=None,
    help="Optional cap on items per dataset (useful for smoke tests).",
)
@click.option(
    "--answer-score-mode",
    type=click.Choice(["semantic", "normalized", "exact"]),
    default="semantic",
    show_default=True,
    help="How to score answer correctness for `accuracy` (default: semantic).",
)
@click.option(
    "--semantic-threshold",
    type=float,
    default=0.6,
    show_default=True,
    help="Threshold for semantic matching (SequenceMatcher ratio).",
)
@click.option(
    "--semantic/--no-semantic",
    default=True,
    show_default=True,
    help="Whether to include semantic accuracy in the metrics.",
)
@click.option(
    "--fallback-max-uses",
    type=int,
    default=0,
    show_default=True,
    help="Fail the run when fallback normalization/inference count exceeds this threshold (-1 disables).",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval",
    show_default=True,
    help="Base directory for metrics outputs.",
)
def eval_run_rag(
    manifest: Path,
    dataset_id: str | None,
    provider: str,
    model: str,
    top_k: int,
    retrieval_mode: str | None,
    compare_retrieval_modes: bool,
    max_items: int | None,
    answer_score_mode: str,
    semantic_threshold: float,
    semantic: bool,
    fallback_max_uses: int,
    out_dir: Path,
) -> None:
    """Run RAG-based evals for each dataset in the manifest."""
    fallback_threshold = None if fallback_max_uses < 0 else fallback_max_uses
    if compare_retrieval_modes and retrieval_mode is not None:
        raise click.ClickException(
            "--compare-retrieval-modes cannot be combined with --retrieval-mode"
        )

    try:
        from eval.validate_datasets import ensure_valid_datasets
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    try:
        manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - manifest parsing errors
        raise click.ClickException(f"Failed to read manifest: {exc}")

    dataset_entries = manifest_obj.get("datasets", []) or []
    if dataset_id:
        dataset_entries = [
            entry for entry in dataset_entries if entry.get("id") == dataset_id
        ]
        if not dataset_entries:
            raise click.ClickException(f"Dataset not found: {dataset_id}")
        dataset_ids: list[str] | None = [dataset_id]
    else:
        dataset_ids = None

    try:
        ensure_valid_datasets(
            manifest_path=manifest,
            schema_path=Path("eval") / "schema.json",
            dataset_ids=dataset_ids,
        )
    except Exception as exc:
        raise click.ClickException(str(exc))

    try:
        from scripts.eval import eval_rag_llm
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    for entry in dataset_entries:
        ds_id = entry.get("id")
        safe_model = eval_rag_llm._safe_name(model or "default")
        suffix = f".{retrieval_mode}" if retrieval_mode else ""
        out_json = Path(out_dir) / f"{ds_id}.rag.{provider}.{safe_model}{suffix}.json"
        out_md = Path(out_dir) / f"{ds_id}.rag.{provider}.{safe_model}{suffix}.md"
        try:
            if compare_retrieval_modes:
                summary_path = eval_rag_llm.compare_retrieval_modes(
                    ds_id,
                    manifest_path=manifest,
                    llm_provider=provider,
                    llm_model=model,
                    top_k=top_k,
                    max_items=max_items,
                    answer_score_mode=answer_score_mode,
                    semantic_threshold=semantic_threshold,
                    semantic=semantic,
                    ablation=None,
                    kg_expansion=None,
                    multihop_only=False,
                    emit_hitl_template=None,
                    trace_pack_required_threshold=None,
                    fallback_max_uses=fallback_threshold,
                    out_root=Path(out_dir) / "retrieval_compare",
                    run_id=eval_rag_llm._safe_name(f"{ds_id}.retrieval"),
                )
                click.echo(f"{ds_id}: wrote {summary_path}")
                continue

            eval_rag_llm.evaluate_dataset(
                ds_id,
                manifest_path=manifest,
                llm_provider=provider,
                llm_model=model,
                top_k=top_k,
                retrieval_mode=retrieval_mode,
                max_items=max_items,
                out_json=out_json,
                out_md=out_md,
                answer_score_mode=answer_score_mode,
                semantic_threshold=semantic_threshold,
                semantic=semantic,
                fallback_max_uses=fallback_threshold,
            )
        except Exception as exc:  # pragma: no cover - bubbled to CLI
            raise click.ClickException(str(exc))
        click.echo(f"{ds_id}: wrote {out_json}")


@eval_group.command(name="fr-coverage")
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("eval") / "manifest.json",
    show_default=True,
    help="Eval manifest describing dataset files.",
)
@click.option(
    "--corpus",
    type=click.Path(path_type=Path),
    default=Path("data") / "fr_sections.jsonl",
    show_default=True,
    help="Corpus JSONL to validate references against.",
)
@click.option(
    "--dataset-id",
    default="all",
    show_default=True,
    help="Dataset id to check, or 'all' for every entry in the manifest.",
)
@click.option(
    "--only-v2/--no-only-v2",
    default=False,
    show_default=True,
    help="When set, only evaluate v2 datasets (id endswith '.v2' or manifest version>=2).",
)
@click.option(
    "--dataset-id-pattern",
    type=str,
    default=None,
    help="Regex filter applied to dataset ids (example: '.*\\\\.v2$').",
)
@click.option(
    "--retrieval-k",
    type=int,
    default=10,
    show_default=True,
    help="Top-k to search in the FAISS retriever when computing ranks.",
)
@click.option(
    "--retrieval-mode",
    type=click.Choice(["dense", "hybrid"]),
    default=None,
    help="Retrieval mode override used for FR coverage checks.",
)
@click.option(
    "--max-items",
    type=int,
    default=None,
    help="Optional cap on items per dataset (useful for smoke checks).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval" / "fr_coverage_report.json",
    show_default=True,
    help="Where to write the FR coverage report.",
)
@click.option(
    "--summary-out",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval" / "fr_coverage_summary.json",
    show_default=True,
    help="Where to write the compact FR coverage summary JSON.",
)
@click.option(
    "--top-missing-sections",
    type=int,
    default=10,
    show_default=True,
    help="How many missing section ids to include in top-N lists.",
)
@click.option(
    "--max-missing-rate",
    type=float,
    default=None,
    help="Strict gate: fail if any dataset missing_in_retrieval_rate exceeds this threshold (e.g. 0.10).",
)
@click.option(
    "--write-blocker-note",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional: write a Markdown note explaining why Phase 1 fails (generated from the report).",
)
@click.option(
    "--fail/--no-fail",
    default=False,
    show_default=True,
    help="Legacy gate: return non-zero when any missing_in_corpus or missing_in_retrieval is non-zero.",
)
def eval_fr_coverage(
    manifest: Path,
    corpus: Path,
    dataset_id: str,
    only_v2: bool,
    dataset_id_pattern: str | None,
    retrieval_k: int,
    retrieval_mode: str | None,
    max_items: int | None,
    out: Path,
    summary_out: Path,
    top_missing_sections: int,
    max_missing_rate: float | None,
    write_blocker_note: Path | None,
    fail: bool,
) -> None:
    """Check FR section coverage + retriever ranks for eval datasets."""

    try:
        from eval.validate_datasets import ensure_valid_datasets
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    selected_dataset_ids: list[str] | None = None
    if dataset_id and dataset_id != "all":
        selected_dataset_ids = [dataset_id]
    try:
        ensure_valid_datasets(
            manifest_path=manifest,
            schema_path=Path("eval") / "schema.json",
            dataset_ids=selected_dataset_ids,
        )
    except Exception as exc:
        raise click.ClickException(str(exc))

    try:
        from earCrawler.eval.coverage_checks import (
            build_fr_coverage_report,
            build_fr_coverage_summary,
            render_fr_coverage_blocker_note,
        )
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    try:
        report = build_fr_coverage_report(
            manifest=manifest,
            corpus=corpus,
            dataset_id=dataset_id,
            only_v2=only_v2,
            dataset_id_pattern=dataset_id_pattern,
            retrieval_k=retrieval_k,
            retrieval_mode=retrieval_mode,
            max_items=max_items,
            top_missing_sections=top_missing_sections,
        )
        summary_obj = build_fr_coverage_summary(
            report, top_missing_sections=top_missing_sections
        )
    except Exception as exc:
        # Still write deterministic artifacts so CI/users can debug quickly.
        out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        failure_report = {
            "manifest_path": str(manifest),
            "corpus_path": str(corpus),
            "dataset_selector": {
                "dataset_id": dataset_id,
                "only_v2": bool(only_v2),
                "dataset_id_pattern": dataset_id_pattern,
            },
            "retrieval_k": retrieval_k,
            "error": str(exc),
        }
        out.write_text(
            json.dumps(failure_report, indent=2, sort_keys=True), encoding="utf-8"
        )
        summary_out.write_text(
            json.dumps(
                {
                    "manifest_path": str(manifest),
                    "corpus_path": str(corpus),
                    "dataset_selector": failure_report["dataset_selector"],
                    "retrieval_k": retrieval_k,
                    "error": str(exc),
                    "datasets": [],
                    "summary": {},
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        if write_blocker_note is not None:
            write_blocker_note.parent.mkdir(parents=True, exist_ok=True)
            write_blocker_note.write_text(
                "# Phase 1 retrieval-coverage blocker note\n\n"
                "## Error\n\n"
                f"{exc}\n",
                encoding="utf-8",
            )
        raise click.ClickException(str(exc))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(
        json.dumps(summary_obj, indent=2, sort_keys=True), encoding="utf-8"
    )

    if write_blocker_note is not None:
        write_blocker_note.parent.mkdir(parents=True, exist_ok=True)
        write_blocker_note.write_text(
            render_fr_coverage_blocker_note(
                report,
                max_missing_rate=max_missing_rate,
                top_missing_sections=top_missing_sections,
            ),
            encoding="utf-8",
        )

    # Human-readable console summary (worst first).
    ds_rows = summary_obj.get("datasets") or []
    click.echo(
        "dataset_id | items | expected | missing_retrieval | missing_rate | missing_corpus"
    )
    click.echo("-" * 88)
    for row in ds_rows:
        ds_id = str(row.get("dataset_id") or "")
        items = int(row.get("num_items") or 0)
        expected = int(row.get("expected_sections") or 0)
        miss_r = int(row.get("num_missing_in_retrieval") or 0)
        miss_c = int(row.get("num_missing_in_corpus") or 0)
        try:
            rate = float(row.get("missing_in_retrieval_rate") or 0.0)
        except Exception:
            rate = 0.0
        click.echo(f"{ds_id} | {items} | {expected} | {miss_r} | {rate:.4f} | {miss_c}")

    summary = summary_obj.get("summary") or {}
    missing_in_corpus = int(summary.get("num_missing_in_corpus") or 0)
    missing_in_retrieval = int(summary.get("num_missing_in_retrieval") or 0)
    worst_ds = summary.get("worst_dataset_id") or "n/a"
    try:
        worst_rate = float(summary.get("worst_missing_in_retrieval_rate") or 0.0)
    except Exception:
        worst_rate = 0.0
    click.echo(
        f"overall: missing_in_corpus={missing_in_corpus}, missing_in_retrieval={missing_in_retrieval}, "
        f"worst_dataset={worst_ds} worst_missing_rate={worst_rate:.4f}"
    )
    top_missing = summary.get("top_missing_sections") or []
    if top_missing:
        click.echo("top_missing_sections:")
        for row in top_missing[:top_missing_sections]:
            if isinstance(row, dict):
                click.echo(f"  - {row.get('section_id')}: {row.get('count')}")
    click.echo(f"wrote: report={out} summary={summary_out}")

    if max_missing_rate is not None and worst_rate > float(max_missing_rate):
        raise click.ClickException(
            f"FR coverage Phase 1 gate failed: worst missing_in_retrieval_rate {worst_rate:.4f} > {float(max_missing_rate):.4f}"
        )
    if fail and (missing_in_corpus or missing_in_retrieval):
        raise click.ClickException(
            "FR coverage legacy gate failed (missing counts non-zero)"
        )


@eval_group.command(name="check-grounding")
@click.option(
    "--eval-json",
    "eval_json",
    type=click.Path(path_type=Path),
    required=True,
    help="Eval JSON emitted by `earctl eval run-rag`.",
)
@click.option(
    "--min-grounded-rate",
    type=float,
    default=1.0,
    show_default=True,
    help="Minimum grounded_rate required to pass.",
)
@click.option(
    "--min-expected-hit-rate",
    type=float,
    default=1.0,
    show_default=True,
    help="Minimum expected-section-hit-rate required to pass.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval" / "grounding_contract_report.json",
    show_default=True,
    help="Where to write the grounding contract report.",
)
@click.option(
    "--fail/--no-fail",
    default=True,
    show_default=True,
    help="Whether to return non-zero when thresholds are not met.",
)
def eval_check_grounding(
    eval_json: Path,
    min_grounded_rate: float,
    min_expected_hit_rate: float,
    out: Path,
    fail: bool,
) -> None:
    """Validate label correctness implies grounded retrieval."""

    try:
        from earCrawler.eval.coverage_checks import build_grounding_contract_report
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    try:
        report = build_grounding_contract_report(
            eval_json=eval_json,
            min_grounded_rate=min_grounded_rate,
            min_expected_hit_rate=min_expected_hit_rate,
        )
    except Exception as exc:
        raise click.ClickException(str(exc))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    summary = report.get("summary") or {}
    click.echo(
        "grounded_rate={:.4f} expected_hit_rate={:.4f} contract_pass_rate={:.4f}".format(
            float(summary.get("grounded_rate") or 0.0),
            float(summary.get("expected_section_hit_rate") or 0.0),
            float(summary.get("contract_pass_rate") or 0.0),
        )
    )
    if fail and not report.get("thresholds_ok"):
        raise click.ClickException("grounding contract check failed")


def register_eval_commands(root: click.Group) -> None:
    """Register eval command group on the root CLI."""

    root.add_command(eval_group, name="eval")
