from earCrawler.monitor.utils import normalize_json, stable_hash


def test_normalization_stable():
    payload1 = {"b": " test ", "a": "<p>Hello</p> world"}
    payload2 = {"a": "Hello world", "b": "test"}
    assert normalize_json(payload1) == normalize_json(payload2)
    assert stable_hash(payload1) == stable_hash(payload2)
    payload2["b"] = "changed"
    assert stable_hash(payload1) != stable_hash(payload2)
