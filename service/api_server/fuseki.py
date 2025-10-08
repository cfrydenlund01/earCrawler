from __future__ import annotations

"""Fuseki integration helpers."""

import asyncio
from dataclasses import dataclass
import json
from typing import Any, Dict, Iterable, List, Mapping, Protocol

import httpx

from .templates import TemplateRegistry


from .templates import Template, TemplateRegistry


class FusekiClient(Protocol):
    async def query(self, template: Template, query: str) -> Mapping[str, Any]:
        ...


@dataclass(slots=True)
class HttpFusekiClient:
    endpoint: str
    timeout: float

    async def query(self, template: Template, query: str) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.endpoint,
                content=query.encode("utf-8"),
                headers={"Content-Type": "application/sparql-query"},
            )
            response.raise_for_status()
            return response.json()


class FusekiGateway:
    def __init__(self, registry: TemplateRegistry, client: FusekiClient) -> None:
        self._registry = registry
        self._client = client

    async def select(self, template_name: str, params: Mapping[str, Any]) -> List[Dict[str, Any]]:
        template = self._registry.get(template_name)
        query = template.render(params)
        payload = await self._client.query(template, query)
        return _coerce_bindings(payload)

    async def select_as_raw(self, template_name: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        template = self._registry.get(template_name)
        query = template.render(params)
        return await self._client.query(template, query)


def _coerce_bindings(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    results = []
    bindings = data.get("results", {}).get("bindings", [])
    for binding in bindings:
        row = {key: _normalize_value(value) for key, value in binding.items()}
        results.append(row)
    return results


def _normalize_value(value: Mapping[str, Any]) -> Any:
    vtype = value.get("type")
    raw = value.get("value")
    if vtype == "uri":
        return raw
    if vtype == "literal":
        if "datatype" in value:
            return {"value": raw, "datatype": value["datatype"]}
        if "xml:lang" in value:
            return {"value": raw, "lang": value["xml:lang"]}
        return raw
    return raw


class StubFusekiClient:
    """Simple in-memory client for tests and smoke checks."""

    def __init__(self, responses: Mapping[str, Iterable[Dict[str, Any]]]) -> None:
        self._responses = responses

    async def query(self, template: Template, query: str) -> Mapping[str, Any]:
        await asyncio.sleep(0)
        payload = self._responses.get(template.name)
        if payload is None:
            return {"head": {"vars": []}, "results": {"bindings": []}}
        bindings = [
            {
                key: _to_binding(value)
                for key, value in row.items()
            }
            for row in payload
        ]
        return {"head": {"vars": list(bindings[0].keys()) if bindings else []}, "results": {"bindings": bindings}}


def _to_binding(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict) and {"value", "datatype"} <= set(value):
        return {"type": "literal", "value": value["value"], "datatype": value["datatype"]}
    if isinstance(value, dict) and {"value", "lang"} <= set(value):
        return {"type": "literal", "value": value["value"], "xml:lang": value["lang"]}
    if isinstance(value, str) and value.startswith("http"):
        return {"type": "uri", "value": value}
    if isinstance(value, str):
        return {"type": "literal", "value": value}
    if isinstance(value, (int, float)):
        return {"type": "literal", "value": str(value)}
    return {"type": "literal", "value": json.dumps(value)}
