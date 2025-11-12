"""Fetch Trade.gov entities for monitoring."""

from __future__ import annotations

import argparse
import json
import sys

from api_clients.tradegov_client import TradeGovClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Trade.gov entities")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Maximum results")
    args = parser.parse_args(argv)
    client = TradeGovClient()
    results = client.search(args.query, limit=args.limit)
    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual usage
    raise SystemExit(main())
