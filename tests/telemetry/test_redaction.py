from earCrawler.telemetry.redaction import redact


def test_redaction_scrubs_strings(monkeypatch):
    monkeypatch.setenv("API_KEY", "SECRET")
    data = {
        "command": "run",
        "email": "user@example.com",
        "token": "bearer ABCDEFGHIJKLMNOPQRST",
        "path": "C:/secret/file.txt",
        "url": "https://example.com?q=1",
        "guid": "123e4567-e89b-12d3-a456-426614174000",
        "env": "SECRET",
    }
    red = redact(data)
    assert "email" not in red
    assert "token" not in red
    assert red["command"] == "run"
    assert "path" not in red
    assert "url" not in red
    assert "guid" not in red
