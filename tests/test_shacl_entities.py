from pathlib import Path

from earCrawler.validation.validate_shapes import run_validation


def test_entities_shape_ok():
    repo_root = Path(__file__).resolve().parents[1]
    sample = repo_root / "earCrawler" / "samples" / "sample_entities.ttl"
    result_code = run_validation([sample])
    assert result_code == 0
