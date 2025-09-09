import gzip
import json
from pathlib import Path

from earCrawler.kg import reconcile


def test_thresholds_and_overrides():
    rules = reconcile.load_rules(Path('kg/reconcile/rules.yml'))
    corpus = reconcile.load_corpus(Path('tests/fixtures/reconcile/corpus.json'))
    summary = reconcile.reconcile(corpus, rules, Path('kg/reconcile'))
    assert summary['counts']['auto_merge'] == 1
    assert summary['counts']['review'] >= 1
    assert summary['counts']['reject'] >= 1
    with gzip.open(Path('kg/reconcile/decisions.jsonl.gz'), 'rt', encoding='utf-8') as fh:
        rows = [json.loads(l) for l in fh]
    def find(l,r):
        for row in rows:
            if row['left']==l and row['right']==r:
                return row
    assert find('s1','s2')['decision'] == 'auto_merge'
    assert find('s3','s4')['decision'] == 'reject'
