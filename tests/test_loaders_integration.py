import pytest

from earCrawler.kg.jena_client import JenaClient
from earCrawler.loaders.csl_loader import load_csl_by_query
from earCrawler.loaders.ear_parts_loader import (
    link_entities_to_parts_by_name_contains,
    load_parts_from_fr,
)


@pytest.mark.skip(reason="Requires running Fuseki and valid Trade.gov key")
def test_end_to_end():
    client = JenaClient()
    loaded = load_csl_by_query("Huawei", limit=2, jena=client)
    parts = load_parts_from_fr(
        "Export Administration Regulations",
        jena=client,
        pages=1,
        per_page=5,
    )
    linked = link_entities_to_parts_by_name_contains(
        client,
        "Huawei",
        list(parts)[:1],
    )
    assert loaded >= 0
    assert linked >= 0
