import json
from pathlib import Path

from earCrawler.utils import diff_reports, kg_state


def test_hash_stability(tmp_path):
    f1 = tmp_path / "a.ttl"
    f1.write_text("data")
    f2 = tmp_path / "b.ttl"
    f2.write_text("data")
    h1 = kg_state._hash_file(f1)
    h2 = kg_state._hash_file(f2)
    assert h1 == h2
    f2.write_text("changed")
    h3 = kg_state._hash_file(f2)
    assert h1 != h3


def test_srj_diff_ignores_order(tmp_path):
    left = tmp_path / "l.srj"
    right = tmp_path / "r.srj"
    obj1 = {"results": {"bindings": [{"x": 1}, {"x": 2}]}}
    obj2 = {"results": {"bindings": [{"x": 2}, {"x": 1}]}}
    left.write_text(json.dumps(obj1))
    right.write_text(json.dumps(obj2))
    res = diff_reports.diff_srj(left, right)
    assert res["changed"] is False
