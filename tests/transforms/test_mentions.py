from __future__ import annotations

from earCrawler.transforms.mentions import MentionExtractor


def test_exact_match_scores_max():
    extractor = MentionExtractor()
    strength = extractor.score("Huawei Technologies Co., Ltd. released a notice.", "Huawei Technologies Co Ltd")
    assert strength == 1.0


def test_core_tokens_window_score():
    extractor = MentionExtractor()
    text = "The department of commerce imposed controls affecting Acme International Holdings in the latest rule."
    strength = extractor.score(text, "ACME International Holdings Company")
    assert 0.6 <= strength < 1.0


def test_stopwords_restrict_false_positive():
    extractor = MentionExtractor()
    strength = extractor.score("The international community met to discuss policy.", "International Holdings")
    assert strength == 0.0
