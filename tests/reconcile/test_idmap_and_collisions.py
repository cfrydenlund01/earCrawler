import csv
from pathlib import Path

from rdflib import Graph

from earCrawler.kg import reconcile


def test_idmap_and_collisions():
    rules = reconcile.load_rules(Path("kg/reconcile/rules.yml"))
    corpus = reconcile.load_corpus(Path("tests/fixtures/reconcile/corpus.json"))
    reconcile.reconcile(corpus, rules, Path("kg/reconcile"))
    with open("kg/reconcile/idmap.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    canon_s1 = [r["canonical_id"] for r in rows if r["source_id"] == "s1"][0]
    canon_s2 = [r["canonical_id"] for r in rows if r["source_id"] == "s2"][0]
    assert canon_s1 == canon_s2
    g = Graph()
    g.parse("kg/delta/reconcile-merged.ttl", format="turtle")
    q1 = Path("kg/queries/reconcile_collisions.rq").read_text()
    assert list(g.query(q1)) == []
    q2 = Path("kg/queries/reconcile_unmerged_duplicates.rq").read_text()
    assert list(g.query(q2)) == []
