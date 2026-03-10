from __future__ import annotations

"""Quarantined compatibility import for the legacy ingestion pipeline.

This module is intentionally gated to avoid accidental use. Supported operator
flows are `earctl` command groups such as `jobs`, `corpus`, and `kg`.
"""

import os

if os.getenv("EARCRAWLER_ENABLE_LEGACY_INGESTION") != "1":
    raise RuntimeError(
        "Legacy ingestion module is quarantined. "
        "Use earctl jobs/corpus/kg paths instead, or set "
        "EARCRAWLER_ENABLE_LEGACY_INGESTION=1 for isolated legacy testing."
    )

from earCrawler.experimental.legacy_ingest import Ingestor

__all__ = ["Ingestor"]
