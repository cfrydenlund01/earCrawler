from __future__ import annotations

from pathlib import Path

import pytest

from earCrawler.rag.ecfr_api_fetch import fetch_ecfr_snapshot


def test_fetch_requires_network_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EARCRAWLER_ALLOW_NETWORK", raising=False)
    with pytest.raises(RuntimeError):
        fetch_ecfr_snapshot(tmp_path / "out.jsonl")
