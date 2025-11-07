from __future__ import annotations

from earCrawler.privacy import scrub_text


def test_scrub_text_masks_common_pii_patterns() -> None:
    text = (
        "Contact alice@example.com with token ABCDEFGHIJKLMNOPQRST123 "
        "stored at C:\\Secrets\\file.txt and https://example.com/path?q=secret#frag "
        "GUID 123e4567-e89b-12d3-a456-426614174000 phone 202-555-0101 ssn 123-45-6789"
    )
    cleaned = scrub_text(text)
    assert "[redacted]" in cleaned
    assert "[token]" in cleaned
    assert "[path]" in cleaned
    assert "https://example.com/path" in cleaned and "secret#frag" not in cleaned
    assert "[guid]" in cleaned
    assert "[phone]" in cleaned
    assert "[ssn]" in cleaned


def test_scrub_text_preserves_normal_text() -> None:
    text = "Normal paragraph with no secrets."
    assert scrub_text(text) == text
