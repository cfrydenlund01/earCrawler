from pathlib import Path

from rdflib import Graph


def test_build_ttl_serializes(tmp_path, monkeypatch):
    from earCrawler.pipelines.build_ttl import build_samples
    from earCrawler.utils.io_paths import DIST

    # isolate dist path during test
    monkeypatch.setattr("earCrawler.utils.io_paths.DIST", tmp_path)
    monkeypatch.setattr("earCrawler.pipelines.build_ttl.DIST", tmp_path, raising=False)
    monkeypatch.setattr(
        "earCrawler.pipelines.build_ttl.ensure_dirs",
        lambda: tmp_path.mkdir(exist_ok=True),
    )

    output = build_samples()
    assert output.exists()
    graph = Graph().parse(output.as_posix(), format="turtle")
    assert len(graph) > 0
