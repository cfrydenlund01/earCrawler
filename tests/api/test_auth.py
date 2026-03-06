from __future__ import annotations

from service.api_server.auth import ApiKeyResolver


def test_api_key_resolver_keyring_accepts_matching_labeled_secret(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_API_KEYS", raising=False)
    keyring_data = {"ops": "ops-secret"}
    monkeypatch.setattr(
        "service.api_server.auth.keyring.get_password",
        lambda service_name, label: keyring_data.get(label),
    )

    identity = ApiKeyResolver().resolve("ops:ops-secret")

    assert identity is not None
    assert identity.authenticated is True
    assert identity.api_key_label == "ops"


def test_api_key_resolver_keyring_rejects_wrong_secret(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_API_KEYS", raising=False)
    keyring_data = {"ops": "ops-secret"}
    monkeypatch.setattr(
        "service.api_server.auth.keyring.get_password",
        lambda service_name, label: keyring_data.get(label),
    )

    identity = ApiKeyResolver().resolve("ops:not-the-secret")

    assert identity is None


def test_api_key_resolver_keyring_rejects_wrong_label(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_API_KEYS", raising=False)
    keyring_data = {"ops": "ops-secret"}
    monkeypatch.setattr(
        "service.api_server.auth.keyring.get_password",
        lambda service_name, label: keyring_data.get(label),
    )

    identity = ApiKeyResolver().resolve("reader:ops-secret")

    assert identity is None


def test_api_key_resolver_keyring_rejects_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_API_KEYS", raising=False)
    monkeypatch.setattr(
        "service.api_server.auth.keyring.get_password",
        lambda service_name, label: None,
    )

    identity = ApiKeyResolver().resolve("ops:ops-secret")

    assert identity is None
