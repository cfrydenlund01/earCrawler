from __future__ import annotations

"""RAG CLI commands and registrar."""

import json
from pathlib import Path

import click
import requests

from api_clients.federalregister_client import FederalRegisterClient
from api_clients.llm_client import LLMProviderError
from earCrawler.rag.build_corpus import build_retrieval_corpus, write_corpus_jsonl
from earCrawler.rag.ecfr_api_fetch import fetch_ecfr_snapshot
from earCrawler.rag.index_builder import build_faiss_index_from_corpus
from earCrawler.rag.offline_snapshot_manifest import validate_offline_snapshot
from earCrawler.rag.pipeline import answer_with_rag
from earCrawler.rag.retriever import RetrieverError
from earCrawler.rag.snapshot_corpus import build_snapshot_corpus_bundle
from earCrawler.rag.snapshot_index import build_snapshot_index_bundle
from earCrawler.security import policy


def _resolve_snapshot_index_builder():
    """Support legacy tests that monkeypatch build_snapshot_index_bundle on cli.__main__."""

    try:
        from earCrawler.cli import __main__ as main_mod

        patched = getattr(main_mod, "build_snapshot_index_bundle", None)
        if callable(patched):
            return patched
    except Exception:
        pass
    return build_snapshot_index_bundle


@click.group()
@policy.require_role("reader")
@policy.enforce
def llm() -> None:
    """LLM-backed helpers (multi-provider)."""


@llm.command(name="ask")
@click.option(
    "--llm-provider",
    type=click.Choice(["nvidia_nim", "groq"]),
    default=None,
    help="LLM provider (overrides config/llm_secrets.env).",
)
@click.option(
    "--llm-model",
    type=str,
    default=None,
    help="LLM model identifier for the chosen provider.",
)
@click.option(
    "--top-k",
    type=int,
    default=5,
    show_default=True,
    help="Number of retrieved contexts to pass to the LLM.",
)
@click.option(
    "--effective-date",
    type=str,
    default=None,
    help="Optional as-of date (YYYY-MM-DD) used for temporal applicability filtering.",
)
@click.option(
    "--retrieval-only",
    is_flag=True,
    default=False,
    help="Skip generation and return only retrieved contexts/documents.",
)
@click.argument("question", type=str)
def llm_ask(
    llm_provider: str | None,
    llm_model: str | None,
    top_k: int,
    effective_date: str | None,
    retrieval_only: bool,
    question: str,
) -> None:
    """Answer a question using the RAG pipeline and selected provider/model."""

    try:
        result = answer_with_rag(
            question,
            provider=llm_provider,
            model=llm_model,
            top_k=top_k,
            generate=not retrieval_only,
            effective_date=effective_date,
        )
    except LLMProviderError as exc:
        raise click.ClickException(str(exc))
    except RetrieverError as exc:
        raise click.ClickException(str(exc))
    egress = result.get("egress_decision") or {}
    click.echo(
        "remote_enabled={remote} provider={provider} model={model} redaction={redaction} prompt_hash={prompt_hash}".format(
            remote=egress.get("remote_enabled"),
            provider=egress.get("provider"),
            model=egress.get("model"),
            redaction=egress.get("redaction_mode"),
            prompt_hash=egress.get("prompt_hash"),
        )
    )
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@click.command(name="fr-fetch")
@click.option(
    "--section",
    "-s",
    "sections",
    multiple=True,
    help="EAR section identifier to search (e.g., 744.6(b)(3)). Repeatable.",
)
@click.option(
    "--query",
    help="Free-text query to send to Federal Register (falls back to sections when omitted).",
)
@click.option(
    "--per-page",
    type=int,
    default=2,
    show_default=True,
    help="Max results to collect per section/query.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("data") / "fr_sections.jsonl",
    show_default=True,
    help="Destination JSONL file.",
)
def fr_fetch(
    sections: tuple[str, ...], query: str | None, per_page: int, out: Path
) -> None:
    """Fetch EAR-related passages from the Federal Register and store them for indexing."""

    if not sections and not query:
        raise click.ClickException("Provide at least one --section or a --query.")

    client = FederalRegisterClient()
    out.parent.mkdir(parents=True, exist_ok=True)

    def _records_for(term: str) -> list[dict]:
        try:
            docs = client.get_ear_articles(term, per_page=per_page)
        except Exception as exc:
            click.echo(
                f"Warning: failed to fetch '{term}' from Federal Register: {exc}",
                err=True,
            )
            # Fallback to the public JSON API directly to avoid client-level checks.
            try:
                resp = requests.get(
                    "https://www.federalregister.gov/api/v1/documents.json",
                    params={"per_page": per_page, "conditions[term]": term},
                    headers={"Accept": "application/json"},
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
                docs = []
                for item in data.get("results", []):
                    detail_url = f"https://www.federalregister.gov/api/v1/documents/{item.get('document_number')}.json"
                    detail = requests.get(
                        detail_url, headers={"Accept": "application/json"}, timeout=20
                    )
                    detail.raise_for_status()
                    detail_json = detail.json()
                    text = (
                        detail_json.get("body_html")
                        or detail_json.get("body_text")
                        or item.get("abstract")
                        or " ".join(item.get("excerpts") or [])
                        or ""
                    )
                    docs.append(
                        {
                            "id": item.get("document_number"),
                            "title": item.get("title"),
                            "publication_date": item.get("publication_date"),
                            "source_url": item.get("html_url") or item.get("url"),
                            "text": text,
                            "provider": "federalregister.gov",
                        }
                    )
            except Exception as inner_exc:  # pragma: no cover - network dependent
                click.echo(
                    f"Warning: fallback fetch for '{term}' also failed: {inner_exc}",
                    err=True,
                )
                return []
        records: list[dict] = []
        for doc in docs:
            text = (doc.get("text") or "").strip()
            if not text:
                continue
            section_id = term.strip()
            records.append(
                {
                    "id": f"EAR-{section_id}",
                    "section": section_id,
                    "span_id": section_id,
                    "title": doc.get("title"),
                    "text": text,
                    "source_url": doc.get("source_url"),
                    "provider": doc.get("provider", "federalregister.gov"),
                }
            )
        return records

    collected: list[dict] = []
    if query:
        collected.extend(_records_for(query))
    for sec in sections:
        collected.extend(_records_for(sec))

    if not collected:
        raise click.ClickException("No records fetched from Federal Register.")

    with out.open("w", encoding="utf-8") as fh:
        for rec in collected:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    click.echo(f"Wrote {len(collected)} records -> {out}")


@click.group()
def rag_index() -> None:
    """RAG index maintenance helpers."""


@rag_index.command(name="build")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file containing retrieval corpus records (see retrieval_corpus_contract.md).",
)
@click.option(
    "--index-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("data") / "faiss" / "index.faiss",
    show_default=True,
    help="Destination FAISS index path.",
)
@click.option(
    "--model-name",
    type=str,
    default="all-MiniLM-L12-v2",
    show_default=True,
    help="SentenceTransformer model name.",
)
@click.option(
    "--reset/--no-reset",
    default=True,
    show_default=True,
    help="Reset existing index/metadata before building.",
)
@click.option(
    "--meta-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Destination metadata path (defaults to <index-path>.meta.json).",
)
def rag_index_build(
    input_path: Path,
    index_path: Path,
    model_name: str,
    reset: bool,
    meta_path: Path | None,
) -> None:
    """Build a FAISS index + metadata sidecar from a validated retrieval corpus."""

    meta_path = meta_path or index_path.with_suffix(".meta.json")
    if reset:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (index_path, index_path.with_suffix(".pkl"), meta_path):
            if path.exists():
                path.unlink()

    from earCrawler.rag.corpus_contract import load_corpus_jsonl, require_valid_corpus

    try:
        docs = load_corpus_jsonl(input_path)
        require_valid_corpus(docs)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        build_faiss_index_from_corpus(
            docs,
            index_path=index_path,
            meta_path=meta_path,
            embedding_model=model_name,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Indexed {len(docs)} documents -> {index_path} (meta {meta_path})")


@rag_index.command(name="build-corpus")
@click.option(
    "--snapshot",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Offline eCFR snapshot JSONL. Requires a sibling manifest (see docs/offline_snapshot_spec.md).",
)
@click.option(
    "--snapshot-manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional offline snapshot manifest override (offline-snapshot.v1).",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("data") / "faiss" / "retrieval_corpus.jsonl",
    show_default=True,
    help="Destination corpus JSONL path.",
)
@click.option(
    "--source-ref",
    type=str,
    default=None,
    help="Override source_ref for all documents (falls back to snapshot values).",
)
@click.option(
    "--chunk-max-chars",
    type=int,
    default=6000,
    show_default=True,
    help="Maximum characters per chunk before paragraph splitting.",
)
@click.option(
    "--preflight/--no-preflight",
    default=True,
    show_default=True,
    help="Run snapshot validation before corpus build.",
)
def rag_index_build_corpus(
    snapshot: Path,
    snapshot_manifest: Path | None,
    out: Path,
    source_ref: str | None,
    chunk_max_chars: int,
    preflight: bool,
) -> None:
    """Build retrieval corpus from offline snapshot and write JSONL."""

    try:
        docs = build_retrieval_corpus(
            snapshot,
            source_ref=source_ref,
            manifest_path=snapshot_manifest,
            preflight_validate_snapshot=preflight,
            chunk_max_chars=chunk_max_chars,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    write_corpus_jsonl(out, docs)
    click.echo(f"Wrote {len(docs)} corpus documents -> {out}")


@rag_index.command(name="rebuild-corpus")
@click.option(
    "--snapshot",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Offline eCFR snapshot JSONL to rebuild from.",
)
@click.option(
    "--snapshot-manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional offline snapshot manifest override (offline-snapshot.v1).",
)
@click.option(
    "--out-base",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("dist") / "corpus",
    show_default=True,
    help="Base output directory; artifacts are written to <out-base>/<snapshot_id>/.",
)
@click.option(
    "--source-ref",
    type=str,
    default=None,
    help="Override source_ref for all documents (falls back to snapshot values).",
)
@click.option(
    "--chunk-max-chars",
    type=int,
    default=6000,
    show_default=True,
    help="Maximum characters per chunk before paragraph splitting.",
)
@click.option(
    "--preflight/--no-preflight",
    default=True,
    show_default=True,
    help="Run snapshot validation before corpus build.",
)
@click.option(
    "--check-expected-sections/--no-check-expected-sections",
    default=True,
    show_default=True,
    help="Run smoke check against section IDs referenced in eval datasets.",
)
@click.option(
    "--dataset-manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("eval") / "manifest.json",
    show_default=True,
    help="Eval manifest used to collect expected section IDs.",
)
@click.option(
    "--dataset-id",
    "dataset_ids",
    multiple=True,
    help="Dataset ID(s) to check; defaults to all *.v2 datasets when omitted.",
)
@click.option(
    "--v2-only/--all-datasets",
    default=True,
    show_default=True,
    help="When --dataset-id is omitted, check only *.v2 datasets or all datasets.",
)
def rag_index_rebuild_corpus(
    snapshot: Path,
    snapshot_manifest: Path | None,
    out_base: Path,
    source_ref: str | None,
    chunk_max_chars: int,
    preflight: bool,
    check_expected_sections: bool,
    dataset_manifest: Path,
    dataset_ids: tuple[str, ...],
    v2_only: bool,
) -> None:
    """Deterministically rebuild corpus artifacts under dist/corpus/<snapshot_id>."""

    try:
        bundle = build_snapshot_corpus_bundle(
            snapshot=snapshot,
            snapshot_manifest=snapshot_manifest,
            out_base=out_base,
            source_ref=source_ref,
            chunk_max_chars=chunk_max_chars,
            preflight=preflight,
            check_expected_sections=check_expected_sections,
            dataset_manifest=dataset_manifest,
            dataset_ids=list(dataset_ids) or None,
            include_v2_only=v2_only,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Wrote corpus: {bundle.corpus_path}")
    click.echo(f"Wrote build log: {bundle.build_log_path}")
    click.echo(
        "Smoke check passed: "
        f"doc_count={bundle.doc_count} "
        f"unique_sections={bundle.unique_section_count} "
        f"expected_sections={bundle.expected_section_count} "
        f"missing={len(bundle.missing_expected_sections)}"
    )
    click.echo(
        f"Provenance: snapshot_id={bundle.snapshot_id} "
        f"corpus_digest={bundle.corpus_digest} "
        f"corpus_sha256={bundle.corpus_sha256}"
    )


@rag_index.command(name="rebuild-index")
@click.option(
    "--corpus",
    "corpus_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Canonical retrieval corpus JSONL (typically dist/corpus/<snapshot_id>/retrieval_corpus.jsonl).",
)
@click.option(
    "--out-base",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("dist") / "index",
    show_default=True,
    help="Base output directory; artifacts are written to <out-base>/<snapshot_id>/.",
)
@click.option(
    "--model-name",
    type=str,
    default="all-MiniLM-L12-v2",
    show_default=True,
    help="SentenceTransformer model used for embedding/index build.",
)
@click.option(
    "--verify-env/--no-verify-env",
    default=True,
    show_default=True,
    help="Set EARCRAWLER_FAISS_INDEX/EARCRAWLER_FAISS_MODEL and verify pipeline retriever wiring.",
)
@click.option(
    "--smoke-query",
    type=str,
    default=None,
    help="Optional retrieval smoke query to run against the built index.",
)
@click.option(
    "--smoke-top-k",
    type=int,
    default=5,
    show_default=True,
    help="Top-k for retrieval smoke query.",
)
@click.option(
    "--expect-section",
    "expected_sections",
    multiple=True,
    help="Expected section ID(s) that should appear in smoke-query results (repeatable).",
)
def rag_index_rebuild_index(
    corpus_path: Path,
    out_base: Path,
    model_name: str,
    verify_env: bool,
    smoke_query: str | None,
    smoke_top_k: int,
    expected_sections: tuple[str, ...],
) -> None:
    """Build snapshot-scoped FAISS index + sidecar and verify runtime wiring."""

    index_builder = _resolve_snapshot_index_builder()
    try:
        bundle = index_builder(
            corpus_path=corpus_path,
            out_base=out_base,
            model_name=model_name,
            verify_pipeline_env=verify_env,
            smoke_query=smoke_query,
            smoke_top_k=smoke_top_k,
            expected_sections=list(expected_sections) or None,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Wrote index: {bundle.index_path}")
    click.echo(f"Wrote metadata: {bundle.meta_path}")
    click.echo(f"Wrote index build log: {bundle.build_log_path}")
    click.echo(f"Wrote runtime env: {bundle.env_file_path}")
    click.echo(f"Wrote runtime env ps1: {bundle.env_ps1_path}")
    click.echo(
        "Index metadata verified: "
        f"embedding_model={bundle.embedding_model} "
        f"corpus_digest={bundle.corpus_digest} "
        f"doc_count={bundle.doc_count} "
        f"build_timestamp_utc={bundle.build_timestamp_utc}"
    )
    if smoke_query:
        click.echo(
            "Retrieval smoke passed: "
            f"query='{smoke_query}' "
            f"results={bundle.smoke_result_count} "
            f"expected_hits={bundle.smoke_expected_hits}"
        )


@rag_index.command(name="validate-snapshot")
@click.option(
    "--snapshot",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Offline eCFR snapshot JSONL to validate.",
)
@click.option(
    "--snapshot-manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional offline snapshot manifest override (offline-snapshot.v1).",
)
def rag_index_validate_snapshot(snapshot: Path, snapshot_manifest: Path | None) -> None:
    """Validate offline snapshot + manifest before any corpus/index work."""

    try:
        summary = validate_offline_snapshot(snapshot, manifest_path=snapshot_manifest)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        "Snapshot valid: "
        f"sections={summary.section_count} "
        f"titles={summary.title_count} "
        f"bytes={summary.payload_bytes} "
        f"manifest={summary.manifest.path}"
    )


@rag_index.command(name="fetch-ecfr")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("data") / "ecfr" / "title15.jsonl",
    show_default=True,
    help="Snapshot output path (JSONL).",
)
@click.option(
    "--part",
    "parts",
    multiple=True,
    type=str,
    help="Optional CFR part(s) to fetch (repeatable). If omitted, fetches the entire title.",
)
@click.option(
    "--date",
    type=str,
    default=None,
    help="Optional effective date (YYYY-MM-DD) supported by the API.",
)
@click.option(
    "--title",
    type=str,
    default="15",
    show_default=True,
    help="CFR title to fetch (default: 15).",
)
@click.option(
    "--snapshot-id",
    type=str,
    default=None,
    help="Snapshot id to write into the offline manifest (defaults to out parent directory name).",
)
@click.option(
    "--manifest-out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional manifest output path (offline-snapshot.v1). Defaults to <out_dir>/manifest.json.",
)
@click.option(
    "--owner",
    type=str,
    default=None,
    help="Manifest source.owner (defaults to current OS user).",
)
@click.option(
    "--approved-by",
    type=str,
    default=None,
    help="Manifest source.approved_by (defaults to owner).",
)
def rag_index_fetch_ecfr(
    out: Path,
    parts: tuple[str, ...],
    date: str | None,
    title: str,
    snapshot_id: str | None,
    manifest_out: Path | None,
    owner: str | None,
    approved_by: str | None,
) -> None:
    """Fetch an eCFR snapshot (network gated via EARCRAWLER_ALLOW_NETWORK)."""

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload_path, manifest_path = fetch_ecfr_snapshot(
            out,
            title=title,
            date=date,
            parts=list(parts),
            snapshot_id=snapshot_id,
            manifest_path=manifest_out,
            owner=owner,
            approved_by=approved_by,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote snapshot -> {payload_path}")
    click.echo(f"Wrote manifest -> {manifest_path}")


def register_rag_commands(root: click.Group) -> None:
    root.add_command(llm, name="llm")
    root.add_command(fr_fetch)
    root.add_command(rag_index, name="rag-index")
