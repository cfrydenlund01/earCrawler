"""Fetch Federal Register EAR articles for monitoring."""

from __future__ import annotations

import argparse
import json
import sys

from api_clients.federalregister_client import FederalRegisterClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Federal Register EAR content")
    parser.add_argument("term", help="Search term")
    parser.add_argument("--per-page", type=int, default=5, dest="per_page")
    args = parser.parse_args(argv)
    client = FederalRegisterClient()
    results = client.get_ear_articles(args.term, per_page=args.per_page)
    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual usage
    raise SystemExit(main())
