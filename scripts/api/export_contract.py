"""Utility for exporting OpenAPI JSON and a Postman collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml


def _build_postman_collection(base_url: str) -> Dict[str, Any]:
    """Create a minimal Postman collection that mirrors the facade routes."""

    def _request(
        name: str,
        method: str,
        path: str,
        *,
        description: str = "",
        query: Dict[str, tuple[str, str]] | None = None,
        body: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        segments = [segment for segment in path.split("/") if segment]
        url: Dict[str, Any] = {
            "raw": f"{{{{base_url}}}}{path}",
            "host": ["{{base_url}}"],
            "path": segments,
        }
        if query:
            url["query"] = [
                {"key": key, "value": value, "description": desc}
                for key, (value, desc) in query.items()
            ]
        request = {
            "name": name,
            "request": {
                "method": method,
                "header": [],
                "url": url,
                "description": description,
            },
        }
        if body is not None:
            request["request"]["body"] = {
                "mode": "raw",
                "raw": json.dumps(body, indent=2),
                "options": {"raw": {"language": "json"}},
            }
        return request

    variables: Iterable[Dict[str, Any]] = (
        {
            "key": "base_url",
            "value": base_url,
            "type": "string",
            "description": "FastAPI facade base URL",
        },
        {
            "key": "api_key",
            "value": "",
            "type": "string",
            "description": "Optional X-Api-Key for elevated quotas",
        },
        {
            "key": "entity_id",
            "value": "urn:ear:entity:demo",
            "type": "string",
            "description": "Sample KG entity identifier",
        },
        {
            "key": "search_query",
            "value": "export controls",
            "type": "string",
            "description": "Default /v1/search query string",
        },
    )

    items = [
        _request("Health", "GET", "/health", description="Liveness/readiness probe"),
        _request(
            "Search",
            "GET",
            "/v1/search",
            description="Label search against curated indexes",
            query={
                "q": ("{{search_query}}", "Search term"),
                "limit": ("5", "Result cap"),
            },
        ),
        _request(
            "Get Entity",
            "GET",
            "/v1/entities/{{entity_id}}",
            description="Fetch curated entity projection",
        ),
        _request(
            "Lineage",
            "GET",
            "/v1/lineage/{{entity_id}}",
            description="Retrieve provenance edges for an entity",
        ),
        _request(
            "SPARQL Template",
            "POST",
            "/v1/sparql",
            description="Execute allowlisted SPARQL template by name",
            body={
                "template": "search_entities",
                "parameters": {"q": "{{search_query}}", "limit": 5},
            },
        ),
        _request(
            "RAG Query",
            "POST",
            "/v1/rag/query",
            description="Retrieve cached RAG answers with lineage metadata",
            body={
                "query": "What changed in Part 734?",
                "top_k": 3,
                "include_lineage": True,
            },
        ),
    ]

    return {
        "info": {
            "name": "EarCrawler API",
            "_postman_id": "earcrawler-api-contract",
            "description": "Collection derived from service/openapi/openapi.yaml",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "auth": {
            "type": "apikey",
            "apikey": [
                {"key": "value", "value": "{{api_key}}", "type": "string"},
                {"key": "key", "value": "X-Api-Key", "type": "string"},
                {"key": "in", "value": "header", "type": "string"},
            ],
        },
        "variable": list(variables),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export OpenAPI JSON + Postman artifacts from the canonical YAML spec."
    )
    parser.add_argument(
        "--openapi-yaml",
        type=Path,
        default=Path("service/openapi/openapi.yaml"),
        help="Path to the canonical OpenAPI YAML file.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("docs/api/openapi.json"),
        help="Destination path for the OpenAPI JSON document.",
    )
    parser.add_argument(
        "--postman-out",
        type=Path,
        default=Path("docs/api/postman_collection.json"),
        help="Destination path for the Postman collection.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:9001",
        help="Default base URL embedded in the Postman variables.",
    )
    args = parser.parse_args()

    spec_data = yaml.safe_load(args.openapi_yaml.read_text(encoding="utf-8"))
    args.json_out.write_text(json.dumps(spec_data, indent=2), encoding="utf-8")

    postman = _build_postman_collection(args.base_url)
    args.postman_out.write_text(json.dumps(postman, indent=2), encoding="utf-8")

    print(f"Wrote {args.json_out}")
    print(f"Wrote {args.postman_out}")


if __name__ == "__main__":
    main()
