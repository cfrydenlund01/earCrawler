from __future__ import annotations

"""Top-level CLI exposing NSF parser and reports commands."""

import importlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Set

import click
import requests

from earCrawler import __version__
from earCrawler.core.nsf_case_parser import NSFCaseParser
from earCrawler.cli.ear_fetch import fetch_entities, fetch_ear, warm_cache
from earCrawler.cli import reports_cli
from earCrawler.analytics import reports as analytics_reports
from earCrawler.kg import fuseki
from earCrawler.kg.sparql import SPARQLClient
from earCrawler.kg import emit_ear, emit_nsf
from earCrawler.telemetry.hooks import install as install_telem
from earCrawler.cli.telemetry import telemetry, crash_test
from earCrawler.cli.gc import gc

try:  # optional
    from earCrawler.cli import reconcile_cmd
except Exception:  # pragma: no cover
    reconcile_cmd = None
from earCrawler.security import policy
from earCrawler.cli.auth import auth
from earCrawler.cli.api_service import api as api_cmd
from earCrawler.cli.policy_cmd import policy_cmd
from earCrawler.cli.audit import audit
from earCrawler.cli import perf

from earCrawler.eval import run_eval as eval_core
from api_clients.llm_client import LLMProviderError
from earCrawler.rag.pipeline import answer_with_rag
from api_clients.federalregister_client import FederalRegisterClient
from api_clients.tradegov_client import TradeGovClient
from earCrawler.rag.retriever import Retriever

install_telem()


@click.group()
@click.version_option(__version__)
def cli() -> None:  # pragma: no cover - simple wrapper
    """earCrawler command line."""


@cli.command()
@policy.require_role("reader")
@policy.enforce
def diagnose() -> None:
    """Print deterministic diagnostic information."""
    from earCrawler.telemetry import config as tconfig

    cfg = tconfig.load_config()
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "earCrawler": __version__,
        "telemetry": {
            "enabled": cfg.enabled,
            "spool_dir": cfg.spool_dir,
            "files": len(list(Path(cfg.spool_dir).glob("*"))) if cfg.enabled else 0,
        },
    }
    click.echo(json.dumps(info, sort_keys=True, indent=2))


@cli.command(name="nsf-parse")
@click.option(
    "--fixtures",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing ORI HTML fixtures.",
)
@click.option(
    "--out",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Output directory for parsed cases.",
)
@click.option("--live", default=False, show_default=True, type=bool)
def nsf_parse(fixtures: Path, out: Path, live: bool) -> None:
    """Parse NSF/ORI case files to JSON."""
    parser = NSFCaseParser()
    cases = parser.run(fixtures, live=live)
    out.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case_id = case.get("case_number") or f"case_{cases.index(case)}"
        with (out / f"{case_id}.json").open("w", encoding="utf-8") as fh:
            json.dump(case, fh, ensure_ascii=False, indent=2)
    click.echo(f"Parsed {len(cases)} cases")


# Expose existing reports commands under "reports" group
cli.add_command(reports_cli.reports, name="reports")
cli.add_command(fetch_entities)
cli.add_command(fetch_ear)
cli.add_command(warm_cache)
cli.add_command(telemetry)
cli.add_command(crash_test)
cli.add_command(gc)
if reconcile_cmd is not None:
    cli.add_command(reconcile_cmd.reconcile, name="reconcile")
cli.add_command(auth)
cli.add_command(policy_cmd, name="policy")
cli.add_command(audit)
cli.add_command(perf.perf, name="perf")
bundle_cli = importlib.import_module("earCrawler.cli.bundle")
cli.add_command(bundle_cli.bundle, name="bundle")
jobs_cli = importlib.import_module("earCrawler.cli.jobs")
cli.add_command(jobs_cli.jobs, name="jobs")
integrity_cli = importlib.import_module("earCrawler.cli.integrity")
cli.add_command(integrity_cli.integrity, name="integrity")
corpus_cli = importlib.import_module("earCrawler.cli.corpus")
cli.add_command(corpus_cli.corpus, name="corpus")
cli.add_command(api_cmd, name="api")


def _collect_evidence_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    tasks: Set[str] = set()
    doc_spans: Set[tuple[str, str]] = set()
    kg_nodes: Set[str] = set()
    kg_paths: Set[str] = set()
    for item in items:
        task = str(item.get("task") or "").strip()
        if task:
            tasks.add(task)
        evidence = item.get("evidence") or {}
        for span in evidence.get("doc_spans", []):
            doc_id = str(span.get("doc_id") or "").strip()
            span_id = str(span.get("span_id") or "").strip()
            if doc_id and span_id:
                doc_spans.add((doc_id, span_id))
        for node in evidence.get("kg_nodes", []):
            node_str = str(node or "").strip()
            if node_str:
                kg_nodes.add(node_str)
        for path in evidence.get("kg_paths", []):
            path_str = str(path or "").strip()
            if path_str:
                kg_paths.add(path_str)
    return {
        "tasks": sorted(tasks),
        "doc_spans": [
            {"doc_id": doc, "span_id": span} for doc, span in sorted(doc_spans)
        ],
        "kg_nodes": sorted(kg_nodes),
        "kg_paths": sorted(kg_paths),
    }


@cli.command(name="crawl")
@click.option(
    "--sources",
    "-s",
    multiple=True,
    metavar="[SOURCE1 [SOURCE2]...]",
    required=True,
    help="Which corpus loaders to run (ear, nsf, ...).",
)
@click.option(
    "--out",
    "-o",
    type=str,
    default="data",
    show_default=True,
    help="Output directory for JSONL/index files.",
)
@click.option(
    "--fixtures",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("tests/fixtures"),
    show_default=True,
    help="Fixture directory for NSF loader.",
)
@click.option(
    "--live",
    is_flag=True,
    default=False,
    help="Enable live HTTP fetching (disabled by default).",
)
def crawl(sources: tuple[str, ...], out: str, fixtures: Path, live: bool) -> None:
    """Load paragraphs from selected sources and print counts."""
    from api_clients.federalregister_client import FederalRegisterClient
    from earCrawler.core.ear_loader import EARLoader
    from earCrawler.core.nsf_loader import NSFLoader

    total = 0
    if "ear" in sources:
        client = FederalRegisterClient()
        loader = EARLoader(client, query="export administration regulations")
        count = len(loader.run(fixtures_dir=fixtures, live=live, output_dir=out))
        click.echo(f"ear: {count} paragraphs")
        total += count
    if "nsf" in sources:
        parser = NSFCaseParser()
        loader = NSFLoader(parser, fixtures)
        count = len(loader.run(fixtures_dir=fixtures, live=live, output_dir=out))
        click.echo(f"nsf: {count} paragraphs")
        total += count
    click.echo(f"total: {total} paragraphs")


@cli.command(name="report")
@click.option(
    "--sources",
    "-s",
    multiple=True,
    required=True,
    help="Sources to analyze (ear, nsf, ...).",
)
@click.option(
    "--type",
    "report_type",
    type=click.Choice(["top-entities", "term-frequency", "cooccurrence"]),
    required=True,
    help="Type of report to generate.",
)
@click.option(
    "--entity",
    "entity_type",
    type=click.Choice(["ORG", "PERSON", "GRANT"]),
    required=False,
    help="Entity type (for top-entities and cooccurrence reports).",
)
@click.option("--n", default=10, show_default=True, help="Top n entries to return.")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Write JSON output to file instead of stdout.",
)
def report(
    sources: tuple[str, ...],
    report_type: str,
    entity_type: str | None,
    n: int,
    out: Path | None,
) -> None:
    """Generate analytics reports over stored corpora."""
    results: dict[str, object] = {}
    for src in sources:
        if report_type == "top-entities":
            if entity_type is None:
                raise click.UsageError("--entity required for top-entities")
            results[src] = analytics_reports.top_entities(src, entity_type, n)
        elif report_type == "term-frequency":
            results[src] = analytics_reports.term_frequency(src, n)
        elif report_type == "cooccurrence":
            if entity_type is None:
                raise click.UsageError("--entity required for cooccurrence")
            mapping = analytics_reports.cooccurrence(src, entity_type)
            results[src] = {k: sorted(v) for k, v in mapping.items()}

    if out:
        out.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    for src, data in results.items():
        click.echo(f"## {src}")
        if report_type == "cooccurrence":
            for name, others in data.items():
                click.echo(f"{name}\t{', '.join(others)}")
        else:
            for name, count in data:
                click.echo(f"{name}\t{count}")


@cli.command(name="kg-export")
@click.option("--data-dir", default="data", help="Crawl JSONL directory.")
@click.option("--out-ttl", default="kg/ear_triples.ttl", help="Output TTL file.")
def kg_export(data_dir: str, out_ttl: str) -> None:
    """Export paragraphs & entities to Turtle for Jena TDB2."""
    from pathlib import Path
    from earCrawler.kg.triples import export_triples

    export_triples(Path(data_dir), Path(out_ttl))
    click.echo(f"Written triples to {out_ttl}")


@click.command()
@click.option("--ttl", "-t", default="kg/ear_triples.ttl", help="Turtle file to load.")
@click.option("--db", "-d", default="db", help="TDB2 DB directory.")
@click.option(
    "--no-auto-install",
    is_flag=True,
    default=False,
    help="Disable auto-download of Apache Jena; fail if not present.",
)
def kg_load(ttl: str, db: str, no_auto_install: bool) -> None:
    #    """Load Turtle into a local TDB2 store.
    #
    #    Example (PowerShell)::
    #
    #        python -m earCrawler.cli kg-load --ttl kg\ear_triples.ttl --db db
    #    """
    from pathlib import Path
    from earCrawler.kg.loader import load_tdb

    load_tdb(Path(ttl), Path(db), auto_install=not no_auto_install)
    click.echo(f"Loaded {ttl} into TDB2 at {db}")


cli.add_command(kg_load, name="kg-load")


@click.command()
@click.option("--db", "-d", default="db", help="Path to TDB2 database directory.")
@click.option(
    "--dataset",
    default="/ear",
    show_default=True,
    help="Dataset name (must start with '/').",
)
@click.option(
    "--port", "-p", default=3030, show_default=True, type=int, help="Fuseki port."
)
@click.option(
    "--java-opts", default=None, help="Extra JVM opts (e.g., '-Xms1g -Xmx2g')."
)
@click.option(
    "--no-wait",
    is_flag=True,
    help="Do not wait for server health check; start and return immediately.",
)
@click.option(
    "--dry-run", is_flag=True, help="Print the command and exit without launching."
)
def kg_serve(db, dataset, port, java_opts, no_wait, dry_run):
    """
    Serve the local TDB2 store with Fuseki.
    Windows-first: Jena is auto-downloaded to .\\tools\\jena on first run.
    """

    if not dataset.startswith("/"):
        raise click.BadParameter("dataset must start with '/'")
    cmd = fuseki.build_fuseki_cmd(Path(db), dataset, port, java_opts)
    if dry_run:
        click.echo(" ".join(cmd))
        return
    try:
        proc = fuseki.start_fuseki(
            Path(db), dataset=dataset, port=port, wait=not no_wait, java_opts=java_opts
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Fuseki running at http://localhost:{port}{dataset}/sparql")
    if no_wait:
        return
    try:
        proc.wait()
    except KeyboardInterrupt:
        click.echo("Stopping Fuseki...")
        proc.terminate()


cli.add_command(kg_serve, name="kg-serve")


@click.command()
@click.option(
    "--endpoint", default="http://localhost:3030/ear/sparql", show_default=True
)
@click.option(
    "--file", "-f", type=click.Path(exists=True), help="SPARQL query file (.rq)"
)
@click.option("--sparql", "-q", help="Inline SPARQL query string")
@click.option(
    "--form",
    type=click.Choice(["select", "ask", "construct"]),
    default="select",
    show_default=True,
)
@click.option(
    "--out",
    "-o",
    type=click.Path(),
    default="data/query_results.json",
    show_default=True,
    help="Output file (.json for SELECT/ASK; .nt for CONSTRUCT)",
)
def kg_query(endpoint, file, sparql, form, out):
    """
    Run a SPARQL query against the Fuseki endpoint and write results to .\\data\\.
    """

    if bool(file) == bool(sparql):
        raise click.UsageError("Provide exactly one of --file or --sparql")
    query = Path(file).read_text(encoding="utf-8") if file else sparql
    if form == "construct" and out == "data/query_results.json":
        out = "data/construct.nt"
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    client = SPARQLClient(endpoint)
    try:
        if form == "select":
            data = client.select(query)
            out_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            click.echo(f"{len(data.get('results', {}).get('bindings', []))} rows")
        elif form == "ask":
            boolean = client.ask(query)
            out_path.write_text(json.dumps({"boolean": boolean}), encoding="utf-8")
            click.echo(str(boolean))
        else:  # construct
            text = client.construct(query)
            out_path.write_text(text, encoding="utf-8")
            click.echo(f"Wrote {out_path}")
    except RuntimeError as exc:
        raise click.ClickException(str(exc))


cli.add_command(kg_query, name="kg-query")


def _iter_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                items.append(json.loads(stripped))
    return items


@cli.group(name="eval")
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
def eval_verify_evidence(manifest: Path, corpus: Path, dataset_id: str, out: Path) -> None:
    """Gate eval datasets by verifying evidence <-> corpus alignment."""

    try:
        manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - manifest parsing errors
        raise click.ClickException(f"Failed to read manifest: {exc}")

    dataset_entries = manifest_obj.get("datasets", [])
    if dataset_id != "all":
        dataset_entries = [entry for entry in dataset_entries if entry.get("id") == dataset_id]
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
        from earCrawler.rag.kg_expansion_builder import build_expansion_mapping, write_expansion_mapping
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
    "--max-items",
    type=int,
    default=None,
    help="Optional cap on items per dataset (useful for smoke tests).",
)
@click.option(
    "--semantic/--no-semantic",
    default=True,
    show_default=True,
    help="Whether to include semantic accuracy in the metrics.",
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
    max_items: int | None,
    semantic: bool,
    out_dir: Path,
) -> None:
    """Run RAG-based evals for each dataset in the manifest."""

    try:
        manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - manifest parsing errors
        raise click.ClickException(f"Failed to read manifest: {exc}")

    dataset_entries = manifest_obj.get("datasets", []) or []
    if dataset_id:
        dataset_entries = [entry for entry in dataset_entries if entry.get("id") == dataset_id]
        if not dataset_entries:
            raise click.ClickException(f"Dataset not found: {dataset_id}")

    try:
        from scripts.eval import eval_rag_llm
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    for entry in dataset_entries:
        ds_id = entry.get("id")
        safe_model = eval_rag_llm._safe_name(model or "default")
        out_json = Path(out_dir) / f"{ds_id}.rag.{provider}.{safe_model}.json"
        out_md = Path(out_dir) / f"{ds_id}.rag.{provider}.{safe_model}.md"
        try:
            eval_rag_llm.evaluate_dataset(
                ds_id,
                manifest_path=manifest,
                llm_provider=provider,
                llm_model=model,
                top_k=top_k,
                max_items=max_items,
                out_json=out_json,
                out_md=out_md,
                semantic=semantic,
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
    "--retrieval-k",
    type=int,
    default=10,
    show_default=True,
    help="Top-k to search in the FAISS retriever when computing ranks.",
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
    "--fail/--no-fail",
    default=True,
    show_default=True,
    help="Whether to return non-zero when coverage checks fail.",
)
def eval_fr_coverage(
    manifest: Path,
    corpus: Path,
    dataset_id: str,
    retrieval_k: int,
    max_items: int | None,
    out: Path,
    fail: bool,
) -> None:
    """Check FR section coverage + retriever ranks for eval datasets."""

    try:
        from earCrawler.eval.coverage_checks import build_fr_coverage_report
    except Exception as exc:  # pragma: no cover - import failures
        raise click.ClickException(str(exc))

    try:
        report = build_fr_coverage_report(
            manifest=manifest,
            corpus=corpus,
            dataset_id=dataset_id,
            retrieval_k=retrieval_k,
            max_items=max_items,
        )
    except Exception as exc:
        raise click.ClickException(str(exc))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    summary = report.get("summary") or {}
    missing_in_corpus = int(summary.get("missing_in_corpus") or 0)
    missing_in_retrieval = int(summary.get("missing_in_retrieval") or 0)
    click.echo(
        f"{dataset_id}: missing_in_corpus={missing_in_corpus}, missing_in_retrieval={missing_in_retrieval}"
    )
    if fail and (missing_in_corpus or missing_in_retrieval):
        raise click.ClickException("FR coverage check failed")


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


@cli.command(name="eval-benchmark")
@click.option(
    "--dataset-id",
    type=str,
    help="Dataset ID from eval/manifest.json (e.g., entity_obligations.v1).",
)
@click.option(
    "--data-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Override dataset path (JSONL). If omitted, resolves from manifest.",
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=Path("eval") / "manifest.json",
    show_default=True,
    help="Path to eval manifest describing datasets and KG state.",
)
@click.option(
    "--model-path",
    type=str,
    default="sshleifer/tiny-gpt2",
    show_default=True,
    help="Model to evaluate (HF hub path or local directory).",
)
@click.option(
    "--out-json",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval" / "benchmark.json",
    show_default=True,
    help="Where to write metrics+metadata JSON.",
)
@click.option(
    "--out-md",
    type=click.Path(path_type=Path),
    default=Path("dist") / "eval" / "benchmark.md",
    show_default=True,
    help="Where to write a short Markdown summary.",
)
@click.option(
    "--explainability-artifacts",
    is_flag=True,
    help="Emit aggregated evidence artifacts and assert by-task coverage.",
)
@click.option(
    "--min-accuracy",
    type=float,
    default=None,
    help="Fail if overall accuracy falls below this threshold.",
)
@click.option(
    "--min-label-accuracy",
    type=float,
    default=None,
    help="Fail if label accuracy falls below this threshold.",
)
def eval_benchmark(
    dataset_id: str | None,
    data_file: Path | None,
    manifest: Path,
    model_path: str,
    out_json: Path,
    out_md: Path,
    explainability_artifacts: bool,
    min_accuracy: float | None,
    min_label_accuracy: float | None,
) -> None:
    """Run the evaluation harness against a dataset and emit metrics + metadata."""

    # Resolve dataset metadata from manifest if needed.
    dataset_meta: dict[str, object] | None = None
    kg_digest: str | None = None
    if manifest.exists():
        try:
            manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
            kg_digest = (manifest_obj.get("kg_state", {}) or {}).get(
                "digest"
            )  # type: ignore[assignment]
            if dataset_id:
                ds_entries = manifest_obj.get("datasets", [])
                for entry in ds_entries:
                    if entry.get("id") == dataset_id:
                        dataset_meta = entry
                        break
        except Exception as exc:  # pragma: no cover - manifest read errors
            raise click.ClickException(f"Failed to read manifest: {exc}")

    resolved_data_file = data_file
    if resolved_data_file is None:
        if dataset_meta and dataset_meta.get("file"):
            candidate = Path(str(dataset_meta["file"]))
            if candidate.is_absolute():
                resolved_data_file = candidate
            elif candidate.exists():
                resolved_data_file = candidate
            else:
                resolved_data_file = manifest.parent / candidate
        else:
            resolved_data_file = Path("eval") / "pilot_items.jsonl"

    if not resolved_data_file.exists():
        raise click.ClickException(f"Dataset not found: {resolved_data_file}")

    # Load dataset
    try:
        items: list[dict[str, object]] = []
        with resolved_data_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                items.append(json.loads(line))
    except Exception as exc:
        raise click.ClickException(f"Failed to load dataset: {exc}")

    # Load model and evaluate
    try:
        tokenizer, model = eval_core.load_model(model_path)
    except RuntimeError as exc:
        # Surface optional dependency guidance cleanly.
        raise click.ClickException(str(exc))
    metrics = eval_core.evaluate(model, tokenizer, items)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    result = {
        **metrics,
        "model_path": model_path,
        "data_file": str(resolved_data_file),
        "dataset_id": dataset_id or (dataset_meta.get("id") if dataset_meta else None),
        "dataset_version": dataset_meta.get("version") if dataset_meta else None,
        "task": dataset_meta.get("task") if dataset_meta else None,
        "num_items": len(items),
        "kg_state_digest": kg_digest,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Write a minimal markdown summary for quick inspection.
    markdown_lines = [
        "| Accuracy | Label Accuracy | Avg Latency (s) | Peak GPU Memory |",
        "|---------:|---------------:|----------------:|----------------:|",
        f"| {result['accuracy']:.4f} | {result.get('label_accuracy', 0.0):.4f} | "
        f"{result['avg_latency']:.4f} | {int(result['peak_gpu_memory'])} |",
        "",
        f"- Dataset: {result.get('dataset_id') or 'n/a'} (task={result.get('task') or 'n/a'})",
        f"- Unanswerable accuracy: {result.get('unanswerable_accuracy', 0.0):.4f}",
        f"- KG digest: {result.get('kg_state_digest') or 'n/a'}",
    ]
    task_breakdown = result.get("by_task") or {}
    if task_breakdown:
        markdown_lines.append("")
        markdown_lines.append("By-task summary:")
        for task, stats in sorted(task_breakdown.items()):
            markdown_lines.append(
                f"- {task}: accuracy={stats['accuracy']:.4f}, "
                f"label_accuracy={stats['label_accuracy']:.4f}, count={int(stats['count'])}"
            )
    out_md.write_text("\n".join(markdown_lines), encoding="utf-8")

    if explainability_artifacts:
        summary = _collect_evidence_summary(items)
        dataset_tasks = set(summary["tasks"])
        by_task = set(result.get("by_task", {}).keys())
        missing_tasks = dataset_tasks.difference(by_task)
        if missing_tasks:
            raise click.ClickException(
                f"Missing tasks in metrics output: {', '.join(sorted(missing_tasks))}"
            )
        evidence_payload = {
            "dataset_id": result.get("dataset_id") or dataset_id or "n/a",
            "kg_state_digest": result.get("kg_state_digest"),
            **summary,
        }
        evidence_path = out_json.with_name(f"{out_json.stem}.evidence.json")
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2), encoding="utf-8"
        )
        click.echo(f"Wrote {evidence_path}")

    threshold_errors = []
    if min_accuracy is not None and result["accuracy"] < float(min_accuracy):
        threshold_errors.append(
            f"accuracy {result['accuracy']:.4f} < required {float(min_accuracy):.4f}"
        )
    if min_label_accuracy is not None and result.get("label_accuracy", 0.0) < float(
        min_label_accuracy
    ):
        threshold_errors.append(
            f"label_accuracy {result.get('label_accuracy', 0.0):.4f} < required {float(min_label_accuracy):.4f}"
        )

    click.echo(f"Wrote {out_json} and {out_md}")
    if threshold_errors:
        raise click.ClickException("; ".join(threshold_errors))


@cli.command(name="kg-emit")
@click.option(
    "--sources",
    "-s",
    multiple=True,
    type=click.Choice(["ear", "nsf"]),
    required=True,
    help="Repeatable: e.g., -s ear -s nsf",
)
@click.option(
    "--in",
    "in_dir",
    "-i",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Input data directory.",
)
@click.option(
    "--out",
    "out_dir",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data") / "kg",
    show_default=True,
    help="Output directory for TTL files.",
)
def kg_emit(sources: tuple[str, ...], in_dir: Path, out_dir: Path) -> None:
    """Emit RDF/Turtle for selected sources."""

    out_dir.mkdir(parents=True, exist_ok=True)
    for src in sources:
        try:
            if src == "ear":
                out_path, count = emit_ear(in_dir, out_dir)
            elif src == "nsf":
                out_path, count = emit_nsf(in_dir, out_dir)
            else:
                raise click.ClickException(f"Unknown source: {src}")
            click.echo(f"{src}: {count} triples -> {out_path}")
        except Exception as exc:
            raise click.ClickException(str(exc))


@cli.group()
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
@click.argument("question", type=str)
def llm_ask(llm_provider: str | None, llm_model: str | None, top_k: int, question: str) -> None:
    """Answer a question using the RAG pipeline and selected provider/model."""

    try:
        result = answer_with_rag(
            question,
            provider=llm_provider,
            model=llm_model,
            top_k=top_k,
        )
    except LLMProviderError as exc:
        raise click.ClickException(str(exc))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@cli.command(name="fr-fetch")
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
def fr_fetch(sections: tuple[str, ...], query: str | None, per_page: int, out: Path) -> None:
    """Fetch EAR-related passages from the Federal Register and store them for indexing."""

    if not sections and not query:
        raise click.ClickException("Provide at least one --section or a --query.")

    client = FederalRegisterClient()
    out.parent.mkdir(parents=True, exist_ok=True)

    def _records_for(term: str) -> list[dict]:
        try:
            docs = client.get_ear_articles(term, per_page=per_page)
        except Exception as exc:
            click.echo(f"Warning: failed to fetch '{term}' from Federal Register: {exc}", err=True)
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
                    detail = requests.get(detail_url, headers={"Accept": "application/json"}, timeout=20)
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
                click.echo(f"Warning: fallback fetch for '{term}' also failed: {inner_exc}", err=True)
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


@cli.group()
def rag_index() -> None:
    """RAG index maintenance helpers."""


@rag_index.command(name="build")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file containing passages with 'text' and 'section'.",
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
def rag_index_build(input_path: Path, index_path: Path, model_name: str, reset: bool) -> None:
    """Build a FAISS index from a JSONL corpus."""

    if reset:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (index_path, index_path.with_suffix(".pkl")):
            if path.exists():
                path.unlink()

    docs: list[dict] = []
    with input_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            text = (item.get("text") or item.get("body") or "").strip()
            if not text:
                continue
            docs.append(
                {
                    "id": item.get("id") or item.get("section") or item.get("span_id"),
                    "section": item.get("section"),
                    "span_id": item.get("span_id"),
                    "text": text,
                    "source_url": item.get("source_url"),
                    "provider": item.get("provider"),
                    "title": item.get("title"),
                }
            )

    if not docs:
        raise click.ClickException("No documents with text found in input.")

    retriever = Retriever(
        TradeGovClient(),
        FederalRegisterClient(),
        model_name=model_name,
        index_path=index_path,
    )
    retriever.add_documents(docs)
    click.echo(f"Indexed {len(docs)} documents -> {index_path} (+ metadata {index_path.with_suffix('.pkl')})")


def main() -> None:  # pragma: no cover - CLI entrypoint
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
