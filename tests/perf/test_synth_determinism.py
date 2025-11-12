from perf.synth import generator
from pathlib import Path


def test_synth_determinism(tmp_path):
    out1 = tmp_path / "out1"
    m1 = generator.generate("S", out1)
    out2 = tmp_path / "out2"
    m2 = generator.generate("S", out2)
    assert m1["hashes"]["ttl"] == m2["hashes"]["ttl"]
    out3 = tmp_path / "out3"
    m3 = generator.generate("M", out3)
    assert m1["hashes"]["ttl"] != m3["hashes"]["ttl"]
    assert m1["nodes"] == generator.COUNTS["S"]
