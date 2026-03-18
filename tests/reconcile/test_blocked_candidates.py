from pathlib import Path
from time import perf_counter

from earCrawler.kg import reconcile


def _load_fixture() -> tuple[dict, list[reconcile.Entity]]:
    rules = reconcile.load_rules(Path("kg/reconcile/rules.yml"))
    corpus = reconcile.load_corpus(Path("tests/fixtures/reconcile/corpus.json"))
    return rules, corpus


def _decision_map(result: dict) -> dict[tuple[str, str], str]:
    return {
        (row["left"], row["right"]): row["decision"]
        for row in result["decisions"]
    }


def _build_benchmark_entities(match_groups: int, singletons: int) -> list[reconcile.Entity]:
    entities: list[reconcile.Entity] = []
    for i in range(match_groups):
        name = f"zxq{i:04d}"
        entities.append(
            reconcile.Entity(
                id=f"m{i:04d}a",
                name=f"{name} corp",
                country="US",
                source="tradegov",
                duns=f"D{i:04d}",
                url=f"http://{name}.example.com",
            )
        )
        entities.append(
            reconcile.Entity(
                id=f"m{i:04d}b",
                name=f"{name} corporation",
                country="US",
                source="federalregister",
                duns=f"D{i:04d}",
                url=f"https://{name}.example.com",
            )
        )
    for i in range(singletons):
        name = f"solo{i:04d}"
        entities.append(
            reconcile.Entity(
                id=f"s{i:04d}",
                name=f"{name} llc",
                country="US",
                source="tradegov",
                duns=f"S{i:04d}",
                url=f"http://{name}.example.org",
            )
        )
    entities.sort(key=lambda item: item.id)
    return entities


def _score_runtime(
    entities: list[reconcile.Entity], rules: dict, *, candidate_mode: str
) -> tuple[int, float]:
    start = perf_counter()
    pairs = reconcile.candidate_pair_indices(
        entities, rules, candidate_mode=candidate_mode
    )
    for left_idx, right_idx in pairs:
        reconcile.score_pair(entities[left_idx], entities[right_idx], rules)
    return len(pairs), perf_counter() - start


def test_blocked_candidates_preserve_fixture_auto_merge_recall() -> None:
    rules, corpus = _load_fixture()
    all_pairs = reconcile.reconcile_pairs(corpus, rules, candidate_mode="all_pairs")
    blocked = reconcile.reconcile_pairs(corpus, rules, candidate_mode="blocked")

    all_decisions = _decision_map(all_pairs)
    blocked_decisions = _decision_map(blocked)
    assert set(blocked_decisions).issubset(set(all_decisions))

    positives = {pair for pair, decision in all_decisions.items() if decision == "auto_merge"}
    predicted = {
        pair for pair, decision in blocked_decisions.items() if decision == "auto_merge"
    }
    true_positives = predicted & positives
    recall = len(true_positives) / len(positives) if positives else 1.0
    precision = len(true_positives) / len(predicted) if predicted else 1.0

    assert recall == 1.0
    assert precision == 1.0
    assert (
        blocked["summary"]["pair_stats"]["candidate_pairs_evaluated"]
        <= all_pairs["summary"]["pair_stats"]["candidate_pairs_evaluated"]
    )


def test_blocked_candidates_reduce_runtime_and_pair_count() -> None:
    rules, _ = _load_fixture()
    entities = _build_benchmark_entities(match_groups=80, singletons=200)

    all_pair_count, all_runtime = _score_runtime(
        entities, rules, candidate_mode="all_pairs"
    )
    blocked_pair_count, blocked_runtime = _score_runtime(
        entities, rules, candidate_mode="blocked"
    )

    assert blocked_pair_count < all_pair_count
    assert blocked_runtime < all_runtime
