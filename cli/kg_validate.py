from __future__ import annotations

"""Legacy compatibility wrapper for the deprecated top-level KG validate CLI."""

from earCrawler.cli.legacy_entrypoints import kg_validate_main as main


if __name__ == "__main__":  # pragma: no cover
    main()
