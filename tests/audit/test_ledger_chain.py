from __future__ import annotations

from pathlib import Path

from earCrawler.audit import ledger, verify


def test_chain_and_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("EARCTL_AUDIT_DIR", str(tmp_path))
    ledger.append_event("cmd", "alice", ["reader"], "diagnose", "", 0, 1)
    ledger.append_event("cmd", "alice", ["reader"], "diagnose", "", 0, 1)
    path = ledger.current_log_path()
    assert verify.verify(path)
    rotated = ledger.rotate()
    assert rotated.exists()
    ledger.append_event("cmd", "alice", ["reader"], "diagnose", "", 0, 1)
    new_path = ledger.current_log_path()
    assert new_path != rotated
    assert verify.verify(new_path)
