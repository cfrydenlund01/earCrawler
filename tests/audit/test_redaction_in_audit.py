from __future__ import annotations

import json

from earCrawler.audit import ledger


def test_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("EARCTL_AUDIT_DIR", str(tmp_path))
    arg = "mytoken1234567890abcdefg alice@example.com https://x.test?q=secret"
    ledger.append_event("cmd", "bob", ["reader"], "diagnose", arg, 0, 1)
    last = list(ledger.tail(1))[0]
    text = json.dumps(last)
    assert "alice@example.com" not in text
    assert "mytoken" not in text
    assert "secret" not in text
    assert "[redacted]" in text
