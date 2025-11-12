from pathlib import Path

from earCrawler.kg import reconcile


def _load():
    rules = reconcile.load_rules(Path("kg/reconcile/rules.yml"))
    corpus = reconcile.load_corpus(Path("tests/fixtures/reconcile/corpus.json"))
    return rules, corpus


def test_normalization():
    assert reconcile.normalize("  ACME Corp. ") == "acme"


def test_blocking_keys():
    entity = reconcile.load_corpus(Path("tests/fixtures/reconcile/corpus.json"))[0]
    keys = reconcile.blocking_keys(entity)
    assert keys["alnum"] == "acme"


def test_scoring_explainability():
    rules, corpus = _load()
    score, feats = reconcile.score_pair(corpus[0], corpus[1], rules)
    assert score > 0
    assert "token_jaccard" in feats
    assert "weight" in feats["token_jaccard"]
