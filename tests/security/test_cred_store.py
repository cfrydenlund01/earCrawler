from __future__ import annotations

import keyring
from keyring.backend import KeyringBackend

from earCrawler.security import cred_store


class DummyKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self._storage = {cred_store.SERVICE: {}}

    def get_password(self, service, name):  # pragma: no cover - simple
        return self._storage.get(service, {}).get(name)

    def set_password(self, service, name, value):  # pragma: no cover - simple
        self._storage.setdefault(service, {})[name] = value

    def delete_password(self, service, name):  # pragma: no cover - simple
        self._storage.get(service, {}).pop(name, None)


def test_roundtrip(monkeypatch):
    keyring.set_keyring(DummyKeyring())
    cred_store.set_secret("FOO", "bar")
    assert cred_store.get_secret("FOO") == "bar"
    assert "FOO" in cred_store.list_secrets()
    cred_store.delete_secret("FOO")
    assert cred_store.get_secret("FOO") is None
