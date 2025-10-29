"""Helpers for recording provenance metadata with delta awareness."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict

from rdflib import Graph, URIRef

from .prov import add_provenance, new_prov_graph, write_prov_files


DEFAULT_MANIFEST = Path("kg/.kgstate/provenance.json")
DEFAULT_PROV_DIR = Path("kg/prov")


@dataclass(frozen=True)
class ProvenanceEntry:
    """Normalized provenance facts for a subject."""

    source_url: str
    provider: str
    retrieved_at: str
    content_hash: str
    request_url: str | None = None


def _utc_iso(dt: datetime | None = None) -> str:
    value = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ProvenanceRecorder:
    """Record provenance entries and avoid redundant rewrites.

    Parameters
    ----------
    manifest_path:
        Location of the JSON manifest containing the last known hashes.
    prov_dir:
        Directory where provenance TTL/NQ artefacts will be written.
    """

    def __init__(
        self,
        *,
        manifest_path: Path | None = None,
        prov_dir: Path | None = None,
    ) -> None:
        self.manifest_path = manifest_path or DEFAULT_MANIFEST
        self.prov_dir = prov_dir or DEFAULT_PROV_DIR
        self._previous = self._load_manifest()
        self._current: Dict[str, ProvenanceEntry] = {}
        self._graph: Graph = new_prov_graph()
        self.changed_subjects: set[str] = set()

    # ------------------------------------------------------------------
    # Manifest helpers

    def _load_manifest(self) -> Dict[str, ProvenanceEntry]:
        if not self.manifest_path.exists():
            return {}
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest: Dict[str, ProvenanceEntry] = {}
        for subject, data in raw.items():
            manifest[subject] = ProvenanceEntry(**data)
        return manifest

    def _write_manifest(self) -> None:
        serialised = {
            subject: entry.__dict__
            for subject, entry in sorted(self._current.items())
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(serialised, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API

    def record(
        self,
        subject: URIRef | str,
        *,
        source_url: str,
        provider_domain: str,
        content_hash: str,
        retrieved_at: str | None = None,
        request_url: str | None = None,
    ) -> bool:
        """Record provenance for ``subject``.

        Returns ``True`` when the hash differs from the previous run, signalling
        that downstream artefacts should be regenerated.
        """

        subject_iri = str(subject)
        if isinstance(retrieved_at, str) and retrieved_at:
            timestamp = retrieved_at if "T" in retrieved_at else retrieved_at + "T00:00:00Z"
        else:
            timestamp = _utc_iso()
        entry = ProvenanceEntry(
            source_url=source_url,
            provider=provider_domain,
            retrieved_at=timestamp,
            content_hash=content_hash,
            request_url=request_url,
        )
        prev = self._previous.get(subject_iri)
        self._current[subject_iri] = entry
        changed = prev is None or prev.content_hash != entry.content_hash
        if changed:
            add_provenance(
                self._graph,
                URIRef(subject_iri),
                source_url=source_url,
                provider_domain=provider_domain,
                request_url=request_url,
                generated_at=timestamp,
                response_sha256=content_hash,
            )
            self.changed_subjects.add(subject_iri)
        return changed

    def flush(self) -> None:
        """Write provenance artefacts if anything changed."""

        self._write_manifest()
        if self.changed_subjects:
            write_prov_files(self._graph, self.prov_dir)

    # ------------------------------------------------------------------
    # Introspection utilities (used by tests)

    def snapshot(self) -> Dict[str, ProvenanceEntry]:
        """Return the manifest for inspection without flushing."""

        return dict(self._current)


__all__ = ["ProvenanceRecorder", "ProvenanceEntry"]
