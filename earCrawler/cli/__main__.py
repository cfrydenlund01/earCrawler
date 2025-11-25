from __future__ import annotations

"""Top-level CLI exposing NSF parser and reports commands."""

import importlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

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
def eval_benchmark(
    dataset_id: str | None,
    data_file: Path | None,
    manifest: Path,
    model_path: str,
    out_json: Path,
    out_md: Path,
) -> None:
    """Run the evaluation harness against a dataset and emit metrics + metadata."""

    # Resolve dataset metadata from manifest if needed.
    dataset_meta: dict[str, object] | None = None
    kg_digest: str | None = None
    if manifest.exists():
        try:
            manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
            kg_digest = (
                manifest_obj.get("kg_state", {}) or {}
            ).get("digest")  # type: ignore[assignment]
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
    click.echo(f"Wrote {out_json} and {out_md}")


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


def main() -> None:  # pragma: no cover - CLI entrypoint
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
