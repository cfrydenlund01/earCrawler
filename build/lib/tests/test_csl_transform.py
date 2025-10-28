from earCrawler.transforms.csl_to_rdf import to_bindings


def test_bindings_minimal():
    bindings = to_bindings({"name": "ACME Ltd", "country": "GB"})
    assert bindings["name"] == "ACME Ltd"
    assert bindings["source"]
    assert bindings["country"] == "GB"
