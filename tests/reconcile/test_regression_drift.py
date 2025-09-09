import json
from pathlib import Path

from earCrawler.kg import reconcile


def test_feature_drift():
    rules = reconcile.load_rules(Path('kg/reconcile/rules.yml'))
    corpus = reconcile.load_corpus(Path('tests/fixtures/reconcile/corpus.json'))
    summary = reconcile.reconcile(corpus, rules, Path('kg/reconcile'))
    baseline = json.loads(Path('tests/fixtures/reconcile/baseline_summary.json').read_text())
    for k, v in baseline['feature_avgs'].items():
        assert abs(summary['feature_avgs'][k] - v) < 1e-6
