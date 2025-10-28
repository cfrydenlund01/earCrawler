import keyring
import pytest

from earCrawler.api_clients.tradegov_client import search_entities


SKIP = keyring.get_password("EAR_AI", "TRADEGOV_API_KEY") is None


@pytest.mark.skipif(SKIP, reason="No Trade.gov subscription key")
def test_search_entities_smoke():
    results = search_entities("Huawei", size=1)
    assert isinstance(results, list)
