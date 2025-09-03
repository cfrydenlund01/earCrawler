"""CLI commands for reconciliation tasks."""

from __future__ import annotations

import json
from pathlib import Path

import click

from earCrawler.kg import reconcile as engine


@click.group()
def reconcile() -> None:
    """Entity reconciliation utilities."""


@reconcile.command()
@click.option(
    "--corpus",
    type=click.Path(path_type=Path, exists=True),
    default=Path("tests/fixtures/reconcile/corpus.json"),
    show_default=True,
    help="Corpus JSON file",
)
def run(corpus: Path) -> None:
    """Execute reconciliation over a corpus."""

    rules = engine.load_rules(Path("kg/reconcile/rules.yml"))
    entities = engine.load_corpus(corpus)
    summary = engine.reconcile(entities, rules, Path("kg/reconcile"))
    click.echo(json.dumps(summary, indent=2))


@reconcile.command()
def report() -> None:
    """Print human readable summary of reconciliation run."""

    path = Path("kg/reports/reconcile-summary.json")
    if not path.exists():
        raise click.ClickException("no reconciliation summary found")
    data = json.loads(path.read_text(encoding="utf-8"))
    click.echo(json.dumps(data, indent=2))
    click.echo("conflicts: kg/reports/reconcile-conflicts.json")


@reconcile.command()
@click.option("--canonical-id", required=True)
def rollback(canonical_id: str) -> None:
    """Emit steps to rollback a merge for a canonical id."""

    idmap = Path("kg/reconcile/idmap.csv")
    if not idmap.exists():
        raise click.ClickException("idmap not found")
    rows = [r.split(",") for r in idmap.read_text(encoding="utf-8").splitlines()[1:]]
    affected = [r[1] for r in rows if r[0] == canonical_id]
    if not affected:
        click.echo("no matches")
        return
    for sid in affected:
        click.echo(f"Remove mapping for {sid} from canonical {canonical_id}")


@reconcile.command()
@click.argument("left")
@click.argument("right")
@click.option(
    "--corpus",
    type=click.Path(path_type=Path, exists=True),
    default=Path("tests/fixtures/reconcile/corpus.json"),
    show_default=True,
)
def explain(left: str, right: str, corpus: Path) -> None:
    """Explain scoring for a pair of IDs."""

    rules = engine.load_rules(Path("kg/reconcile/rules.yml"))
    entities = {e.id: e for e in engine.load_corpus(corpus)}
    l = entities.get(left)
    r = entities.get(right)
    if not l or not r:
        raise click.ClickException("ids not found in corpus")
    score, feats = engine.score_pair(l, r, rules)
    click.echo(json.dumps({"score": score, "features": feats}, indent=2))
