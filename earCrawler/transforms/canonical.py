"""Canonicalization helpers for deterministic IRIs and literals."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_ALIAS_PATH = Path("kg/canonical/aliases.json")
_EMBEDDED_ALIAS_RESOURCE = "kg/data/default_aliases.json"


def _load_alias_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in alias registry: {path}") from None


def _load_embedded_aliases() -> dict:
    try:
        data = resources.files("earCrawler").joinpath(_EMBEDDED_ALIAS_RESOURCE)
    except (AttributeError, ModuleNotFoundError):
        return {}
    try:
        with data.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _normalise_key(text: str) -> str:
    return text.casefold().strip()


class CanonicalRegistry:
    """Registry containing alias mappings for names, countries and programs."""

    def __init__(self, *, alias_path: Path | None = None) -> None:
        if alias_path:
            data = _load_alias_file(Path(alias_path))
        elif DEFAULT_ALIAS_PATH.exists():
            data = _load_alias_file(DEFAULT_ALIAS_PATH)
        else:
            data = _load_embedded_aliases()
        self._name_aliases = {
            _normalise_key(k): v.strip() for k, v in data.get("names", {}).items()
        }
        self._country_aliases = {
            _normalise_key(k): v.strip() for k, v in data.get("countries", {}).items()
        }
        self._program_aliases = {
            _normalise_key(k): v.strip() for k, v in data.get("programs", {}).items()
        }
        self._deprecated_ids = {
            k.strip(): v.strip() for k, v in data.get("deprecated_ids", {}).items()
        }

    # ------------------------------------------------------------------
    # Canonical helpers

    def canonical_name(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        alias = self._name_aliases.get(_normalise_key(value))
        return alias or _title_case(value)

    def canonical_country(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        alias = self._country_aliases.get(_normalise_key(value))
        if alias:
            return alias
        # Normalise common punctuation
        cleaned = re.sub(r"[^A-Za-z\s]", "", value).strip()
        return cleaned.title()

    def canonical_programs(self, programs: Iterable[str] | str | None) -> List[str]:
        if programs is None:
            return []
        if isinstance(programs, str):
            raw = [p.strip() for p in programs.split(",") if p.strip()]
        else:
            raw = [p.strip() for p in programs if p]
        canonical: Dict[str, str] = {}
        for item in raw:
            key = self._program_aliases.get(_normalise_key(item)) or item
            canonical[_normalise_key(key)] = key
        return sorted(canonical.values())

    def canonical_entity(self, record: dict) -> dict:
        canonical = dict(record)
        canonical["name"] = self.canonical_name(record.get("name", ""))
        canonical["country"] = self.canonical_country(record.get("country", ""))
        canonical["programs"] = self.canonical_programs(record.get("programs"))
        return canonical

    def resolve_deprecated(self, entity_id: str) -> str:
        return self._deprecated_ids.get(entity_id, entity_id)


def _title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


__all__ = ["CanonicalRegistry"]
