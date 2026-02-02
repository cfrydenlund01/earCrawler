from __future__ import annotations

"""Optional runtime fetcher for eCFR Title 15 snapshots (network gated)."""

import os
from pathlib import Path


def _require_network() -> None:
    if os.getenv("EARCRAWLER_ALLOW_NETWORK") != "1":
        raise RuntimeError("Network access disabled; set EARCRAWLER_ALLOW_NETWORK=1 to fetch eCFR snapshots.")


def fetch_ecfr_snapshot(out_path: Path, *, title: str = "15", date: str | None = None) -> None:
    """Placeholder network fetcher.

    The project prefers offline snapshots for determinism. This helper is gated by
    EARCRAWLER_ALLOW_NETWORK and currently surfaces a clear error to avoid silent
    network use in tests or CI.
    """

    _require_network()
    raise RuntimeError(
        "Live eCFR API fetch is not implemented in this build. "
        "Provide an approved offline snapshot instead."
    )


__all__ = ["fetch_ecfr_snapshot"]
