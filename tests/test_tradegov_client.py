import os
import keyring
import pytest

from api_clients.tradegov_client import search_entities


SKIP = (
    os.getenv("PYTEST_ALLOW_NETWORK", "0") != "1"
    or keyring.get_password("EAR_AI", "TRADEGOV_API_KEY") is None
)


@pytest.mark.skipif(SKIP, reason="No Trade.gov subscription key")
def test_search_entities_smoke():
    results = search_entities("Huawei", size=1)
    assert isinstance(results, list)
