from pathlib import Path

import rdflib

from earCrawler.kg.export_profiles import export_profiles


def test_export_profiles(tmp_path: Path) -> None:
    ttl = tmp_path / "source.ttl"
    graph = rdflib.Graph()
    graph.parse(
        data="@prefix ex: <http://example.org/> . ex:s ex:p ex:o .", format="turtle"
    )
    graph.serialize(destination=str(ttl), format="turtle")
    out_dir = tmp_path / "out"
    manifest = export_profiles(ttl, out_dir, stem="sample")
    assert (out_dir / "sample.ttl").exists()
    assert (out_dir / "sample.nt").exists()
    assert (out_dir / "sample.ttl.gz").exists()
    assert (out_dir / "sample.nt.gz").exists()
    assert "sample.ttl" in manifest
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "checksums.sha256").exists()
