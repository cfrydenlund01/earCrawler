from __future__ import annotations

from typing import Any, List

import pytest

from api_clients.ear_api_client import EarCrawlerApiClient, EarApiError


class _StubResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any],
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.text = "payload" if content_type != "application/json" else ""

    def json(self) -> dict[str, Any]:
        return self._payload


class _StubSession:
    def __init__(self, responses: List[_StubResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def request(
        self, method, url, params=None, json=None, headers=None, timeout=None
    ):  # noqa: D401 - requests compat
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


def test_client_sets_x_api_key_and_query_params():
    session = _StubSession(
        [
            _StubResponse(payload={"status": "pass"}),
            _StubResponse(payload={"results": [], "total": 0}),
            _StubResponse(payload={"id": "urn:example:entity:1", "edges": []}),
        ]
    )
    client = EarCrawlerApiClient(
        "http://localhost:9001", api_key="dev-token", session=session
    )

    client.health()
    client.search_entities("export controls", limit=5, offset=2)
    client.get_lineage("urn:example:entity:1")

    assert len(session.calls) == 3
    assert session.calls[0]["headers"]["X-Api-Key"] == "dev-token"
    assert session.calls[1]["params"] == {
        "q": "export controls",
        "limit": "5",
        "offset": "2",
    }
    assert session.calls[2]["url"].endswith("/v1/lineage/urn:example:entity:1")


def test_sparql_and_rag_payloads():
    responses = [
        _StubResponse(payload={"head": {}, "results": {}}),
        _StubResponse(payload={"trace_id": "abc", "results": []}),
    ]
    session = _StubSession(responses)
    client = EarCrawlerApiClient("http://localhost:9001", session=session)

    client.run_template("search_entities", parameters={"q": "foo", "limit": 1})
    client.rag_query("export controls", top_k=2, include_lineage=True)

    assert session.calls[0]["json"] == {
        "template": "search_entities",
        "parameters": {"q": "foo", "limit": 1},
    }
    assert session.calls[1]["json"] == {
        "query": "export controls",
        "top_k": 2,
        "include_lineage": True,
    }


def test_error_response_raises():
    session = _StubSession([_StubResponse(payload={"detail": "bad"}, status_code=404)])
    client = EarCrawlerApiClient("http://localhost:9001", session=session)

    with pytest.raises(EarApiError):
        client.get_entity("urn:missing")
