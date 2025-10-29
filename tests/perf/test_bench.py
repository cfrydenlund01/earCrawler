from pathlib import Path

from earCrawler.perf.bench import run_benchmarks


def test_run_benchmarks(tmp_path: Path):
    fixtures = tmp_path / "fixtures"
    kg_dir = fixtures / "kg"
    kg_dir.mkdir(parents=True)
    ttl = kg_dir / "ear_small.ttl"
    ttl.write_text(
        """\n@prefix ear: <https://ear.example.org/schema#> .\n@prefix ent: <https://ear.example.org/entity/> .\n\nent:foo a ear:Entity .\n""",
        encoding="utf-8",
    )
    result = run_benchmarks(fixtures, iterations=1)
    assert "load_ttl" in result.timings
    assert result.timings["load_ttl"] >= 0.0
