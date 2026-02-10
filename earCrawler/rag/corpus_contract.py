from __future__ import annotations

"""Schema + validators for the retrieval corpus contract (retrieval-corpus.v1)."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import json

SCHEMA_VERSION = "retrieval-corpus.v1"

CHUNK_KINDS: tuple[str, ...] = ("section", "subsection", "paragraph")
SOURCE_KINDS: tuple[str, ...] = ("ecfr_snapshot", "ecfr_api", "other")

_SECTION_RE = re.compile(
    r"^(?P<section>\d{3}(?:\.\d+[a-z0-9]*)*)(?P<tails>(?:\([a-z0-9]+\))*)$",
    re.IGNORECASE,
)

_DOC_ID_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,200}$")
_PART_RE = re.compile(r"^\d{3}$")

REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "doc_id",
    "section_id",
    "text",
    "chunk_kind",
    "source",
    "source_ref",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "title",
    "part",
    "url",
    "parent_id",
    "ordinal",
    "tokens_estimate",
    "hash",
)


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    doc_index: int | None = None
    doc_id: str | None = None


def normalize_ear_section_id(raw: object | None) -> str | None:
    """Normalize EAR section identifiers to canonical EAR- prefix form."""

    if raw is None:
        return None

    value = str(raw).strip()
    if not value:
        return None

    value = value.replace("\u00a0", " ")
    value = value.lstrip("§").strip()
    value = re.sub(r"(?i)^15\s*cfr\s*", "", value).strip()

    upper = value.upper()
    if upper.startswith("EAR-"):
        body = value[4:]
    elif upper.startswith("EAR "):
        body = value[4:].strip()
    else:
        body = value

    body = body.lstrip("§").strip().replace(" ", "")
    body = body.rstrip(".")
    if not body:
        return None

    body_lower = body.lower()
    match = _SECTION_RE.match(body_lower)
    if not match:
        return None

    normalized = f"{match.group('section')}{match.group('tails')}".lower()
    return f"EAR-{normalized}"


def normalize_ear_doc_id(raw: object | None) -> str | None:
    """Normalize a doc_id.

    v1 supports either:
    - a canonical section id (example: EAR-736.2(b))
    - a canonical section id + a stable suffix (example: EAR-736.2(b)#p0001)
    """

    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None

    if "#" in value:
        left, suffix = value.split("#", 1)
        left_norm = normalize_ear_section_id(left)
        if not left_norm:
            return None
        suffix_norm = suffix.strip().lower()
        if not suffix_norm or not _DOC_ID_SUFFIX_RE.match(suffix_norm):
            return None
        return f"{left_norm}#{suffix_norm}"

    return normalize_ear_section_id(value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_int_like(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_corpus_documents(docs: Sequence[Mapping[str, object]]) -> list[Issue]:
    """Validate a list of corpus documents against the retrieval contract."""

    issues: list[Issue] = []
    doc_id_by_index: list[str | None] = []
    parent_refs: list[tuple[int, str | None, str | None]] = []

    for idx, doc in enumerate(docs):
        if not isinstance(doc, Mapping):
            issues.append(Issue("invalid_type", "document must be a mapping", idx, None))
            doc_id_by_index.append(None)
            parent_refs.append((idx, None, None))
            continue

        for field in REQUIRED_FIELDS:
            if field not in doc or doc[field] is None:
                issues.append(
                    Issue(
                        "missing_field",
                        f"missing required field '{field}'",
                        idx,
                        str(doc.get("doc_id") or ""),
                    )
                )

        schema_version = doc.get("schema_version")
        if schema_version is not None and schema_version != SCHEMA_VERSION:
            issues.append(
                Issue(
                    "invalid_schema_version",
                    f"schema_version must be '{SCHEMA_VERSION}'",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )

        doc_id_raw = doc.get("doc_id")
        doc_id_norm = normalize_ear_doc_id(doc_id_raw)
        if doc_id_raw is None or not _is_non_empty_string(doc_id_raw):
            issues.append(Issue("invalid_doc_id", "doc_id must be a non-empty string", idx, None))
            doc_id_norm = None
        elif doc_id_norm is None:
            issues.append(
                Issue(
                    "invalid_doc_id",
                    f"doc_id '{doc_id_raw}' is not a canonical EAR identifier",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )
        elif doc_id_norm != str(doc_id_raw):
            issues.append(
                Issue(
                    "invalid_doc_id",
                    f"doc_id must be canonical (expected '{doc_id_norm}')",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )

        section_id_raw = doc.get("section_id")
        section_id_norm = normalize_ear_section_id(section_id_raw)
        expected_part: str | None = None
        if section_id_raw is None or not _is_non_empty_string(section_id_raw):
            issues.append(
                Issue(
                    "invalid_section_id",
                    "section_id must be a non-empty string",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )
        elif section_id_norm is None:
            issues.append(
                Issue(
                    "invalid_section_id",
                    f"section_id '{section_id_raw}' is not a canonical EAR identifier",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )
        elif section_id_norm != str(section_id_raw):
            issues.append(
                Issue(
                    "invalid_section_id",
                    f"section_id must be canonical (expected '{section_id_norm}')",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )
        else:
            expected_part = section_id_norm[len("EAR-") :].split(".", 1)[0]

        if doc_id_norm and section_id_norm:
            doc_id_section = doc_id_norm.split("#", 1)[0]
            if doc_id_section != section_id_norm:
                issues.append(
                    Issue(
                        "doc_id_section_mismatch",
                        f"doc_id section prefix '{doc_id_section}' must equal section_id '{section_id_norm}'",
                        idx,
                        doc_id_norm,
                    )
                )

        part = doc.get("part")
        if part is not None:
            if not _is_non_empty_string(part):
                issues.append(
                    Issue(
                        "invalid_part",
                        "part must be a non-empty string when provided",
                        idx,
                        str(doc.get("doc_id") or ""),
                    )
                )
            else:
                part_str = str(part)
                if not _PART_RE.fullmatch(part_str):
                    issues.append(
                        Issue(
                            "invalid_part",
                            "part must be exactly three digits when provided",
                            idx,
                            str(doc.get("doc_id") or ""),
                        )
                    )
                elif expected_part and part_str != expected_part:
                    issues.append(
                        Issue(
                            "part_section_mismatch",
                            f"part '{part_str}' does not match section_id part '{expected_part}'",
                            idx,
                            str(doc.get("doc_id") or ""),
                        )
                    )

        text = doc.get("text")
        if text is None or not isinstance(text, str):
            issues.append(Issue("invalid_text", "text must be a string", idx, str(doc.get("doc_id") or "")))
        elif not text.strip():
            issues.append(Issue("empty_text", "text must not be empty", idx, str(doc.get("doc_id") or "")))

        chunk_kind = doc.get("chunk_kind")
        if chunk_kind is None or not isinstance(chunk_kind, str):
            issues.append(Issue("invalid_chunk_kind", "chunk_kind must be a string", idx, str(doc.get("doc_id") or "")))
        elif chunk_kind not in CHUNK_KINDS:
            issues.append(
                Issue(
                    "invalid_chunk_kind",
                    f"chunk_kind must be one of {CHUNK_KINDS}",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )

        source = doc.get("source")
        if source is None or not isinstance(source, str):
            issues.append(Issue("invalid_source", "source must be a string", idx, str(doc.get("doc_id") or "")))
        elif source not in SOURCE_KINDS:
            issues.append(
                Issue(
                    "invalid_source",
                    f"source must be one of {SOURCE_KINDS}",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )

        source_ref = doc.get("source_ref")
        if source_ref is None or not isinstance(source_ref, str):
            issues.append(Issue("invalid_source_ref", "source_ref must be a string", idx, str(doc.get("doc_id") or "")))
        elif not source_ref.strip():
            issues.append(Issue("invalid_source_ref", "source_ref must not be empty", idx, str(doc.get("doc_id") or "")))

        parent_id_raw = doc.get("parent_id")
        parent_id_norm = None
        if parent_id_raw is not None:
            if not _is_non_empty_string(parent_id_raw):
                issues.append(
                    Issue(
                        "invalid_parent_id",
                        "parent_id must be a non-empty string when provided",
                        idx,
                        str(doc.get("doc_id") or ""),
                    )
                )
            else:
                parent_id_norm = normalize_ear_doc_id(parent_id_raw)
                if parent_id_norm is None:
                    issues.append(
                        Issue(
                            "invalid_parent_id",
                            f"parent_id '{parent_id_raw}' is not a canonical EAR identifier",
                            idx,
                            str(doc.get("doc_id") or ""),
                        )
                    )
                elif parent_id_norm != str(parent_id_raw):
                    issues.append(
                        Issue(
                            "invalid_parent_id",
                            f"parent_id must be canonical (expected '{parent_id_norm}')",
                            idx,
                            str(doc.get("doc_id") or ""),
                        )
                    )
        parent_refs.append((idx, doc_id_norm, parent_id_norm))
        doc_id_by_index.append(doc_id_norm)

        ordinal = doc.get("ordinal")
        if ordinal is not None and not _is_int_like(ordinal):
            issues.append(Issue("invalid_ordinal", "ordinal must be an integer when provided", idx, str(doc.get("doc_id") or "")))

        tokens_estimate = doc.get("tokens_estimate")
        if tokens_estimate is not None and not _is_int_like(tokens_estimate):
            issues.append(
                Issue(
                    "invalid_tokens_estimate",
                    "tokens_estimate must be an integer when provided",
                    idx,
                    str(doc.get("doc_id") or ""),
                )
            )

    # Duplicate doc_id detection
    seen: dict[str, int] = {}
    for idx, doc_id in enumerate(doc_id_by_index):
        if doc_id is None:
            continue
        if doc_id in seen:
            issues.append(
                Issue(
                    "duplicate_doc_id",
                    f"doc_id '{doc_id}' is duplicated (first seen at index {seen[doc_id]})",
                    idx,
                    doc_id,
                )
            )
        else:
            seen[doc_id] = idx

    valid_doc_ids = {doc_id for doc_id in doc_id_by_index if doc_id}
    for idx, doc_id_norm, parent_norm in parent_refs:
        if parent_norm is None:
            continue
        if parent_norm == doc_id_norm:
            issues.append(Issue("invalid_parent_id", "parent_id cannot reference the same document", idx, doc_id_norm))
            continue
        if parent_norm not in valid_doc_ids:
            issues.append(
                Issue(
                    "parent_missing",
                    f"parent_id '{parent_norm}' not found in corpus",
                    idx,
                    doc_id_norm,
                )
            )

    return issues


def require_valid_corpus(docs: Sequence[Mapping[str, object]]) -> None:
    """Raise ValueError if the corpus is invalid."""

    problems = validate_corpus_documents(docs)
    if not problems:
        return

    lines = []
    for issue in problems:
        prefix = f"[{issue.code}]"
        loc = []
        if issue.doc_index is not None:
            loc.append(f"index={issue.doc_index}")
        if issue.doc_id:
            loc.append(f"doc_id={issue.doc_id}")
        suffix = f" ({', '.join(loc)})" if loc else ""
        lines.append(f"{prefix} {issue.message}{suffix}")

    raise ValueError("retrieval corpus invalid:\n" + "\n".join(lines))


def load_corpus_jsonl(path: Path) -> list[dict]:
    """Strictly load a JSONL corpus file for validation/indexing."""

    path = Path(path)
    if not path.exists():
        raise ValueError(f"Corpus not found: {path}")

    docs: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except Exception as exc:
                raise ValueError(f"{path}:{lineno} invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{lineno} expected object, got {type(obj).__name__}")
            docs.append(obj)
    if not docs:
        raise ValueError(f"No documents found in corpus: {path}")
    return docs


__all__ = [
    "SCHEMA_VERSION",
    "CHUNK_KINDS",
    "SOURCE_KINDS",
    "Issue",
    "normalize_ear_section_id",
    "normalize_ear_doc_id",
    "validate_corpus_documents",
    "require_valid_corpus",
    "load_corpus_jsonl",
]
