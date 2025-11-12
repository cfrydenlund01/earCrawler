from unittest.mock import Mock

import pytest

from api_clients.federalregister_client import (
    FederalRegisterClient,
    FederalRegisterError,
)


def test_html_guard(monkeypatch) -> None:
    client = FederalRegisterClient()
    response = Mock()
    response.headers = {"Content-Type": "text/html"}
    response.raise_for_status.return_value = None
    response.request = Mock(path_url="/test")
    response.json.side_effect = AssertionError("json() should not be called")
    monkeypatch.setattr(client.session, "get", Mock(return_value=response))
    with pytest.raises(FederalRegisterError):
        client._get_json("https://api.federalregister.gov/v1/test", params={})
    response.json.assert_not_called()
