# Retrieval Corpus Contract (v1)

## Purpose
- Define a single, versioned contract for the **retrieval text corpus** that downstream components (FAISS index, RAG, evals, citation rendering) can rely on.
- Make the contract enforceable offline via schema + validation helpers.

## Non-goals
- No ingestion, crawling, chunking, eCFR API work, or FAISS changes.
- No pipeline refactors; this document only specifies the authoritative shape.

## Terminology
- **corpus**: JSONL collection of retrieval documents that can be indexed.
- **document**: one retrieval-ready text chunk.
- **doc_id**: stable identifier for the document; canonical EAR form; unique in a corpus snapshot.
- **section_id**: canonical EAR section id used for citations; MAY equal `doc_id`.
- **chunk_kind**: boundary metadata; one of `section`, `subsection`, `paragraph`.
- **parent_id**: optional `doc_id` of the parent chunk (e.g., paragraph → subsection).
- **source_ref**: provenance string describing the snapshot/date/hash of the originating source.
- **schema_version**: contract version string; MUST be `retrieval-corpus.v1` for this spec.

## Required fields (MUST exist per document)
- `schema_version`: string, MUST equal `retrieval-corpus.v1`.
- `doc_id`: string, canonical EAR id (see Identifier rules). In v1, `doc_id` MUST be unique and is typically equal to `section_id`.
- `section_id`: string, canonical EAR id used for citations; MAY equal `doc_id`.
- `text`: non-empty string containing the chunk text.
- `chunk_kind`: one of `section`, `subsection`, `paragraph`.
- `source`: one of `ecfr_snapshot`, `ecfr_api`, `other`.
- `source_ref`: non-empty string describing the specific snapshot/version/hash.

## Optional fields (MAY be present)
- `title`, `url`, `parent_id`, `ordinal`, `tokens_estimate`, `hash`.

## Identifier rules
- Canonical prefix: `EAR-`.
- Normalized forms (examples):
  - `15 CFR 736.2` → `EAR-736.2`
  - `§ 736.2(b)` / `736.2(b)` → `EAR-736.2(b)`
  - `EAR-736.2(b)` stays as-is.
- `doc_id` forms:
  - Section-level document: `doc_id == section_id` (example: `EAR-736.2(b)`).
  - Chunk-level document: `doc_id == section_id + "#" + suffix` (example: `EAR-736.2(b)#p0001`).
  - Suffix MUST be lowercase ASCII matching `[a-z0-9][a-z0-9:._-]*`.
- Pattern (post-normalization): `EAR-` + `<part>` where `<part>` = 3 digits, optional dot segments, optional repeated parentheses `(letter|digit)`; letters canonicalized to lowercase.
- Stability: `doc_id` MUST be stable across runs for the same `source_ref` (same snapshot/version/hash).
- `doc_id` values MUST be unique within a corpus file.

## Chunk boundary semantics
- `chunk_kind` values:
  - `section`: the CFR section root (e.g., `EAR-736.2`).
  - `subsection`: direct child of a section (e.g., `EAR-736.2(b)`).
  - `paragraph`: lowest chunking unit; MAY carry `ordinal`.
- `parent_id`:
  - MAY be provided; when provided it MUST reference another `doc_id` present in the same corpus.
  - MUST point to the immediate container (e.g., paragraph → subsection).
- `ordinal` (if present): integer conveying ordering among siblings; consumers MAY use it for deterministic sorting.

## Provenance minimum
- `source` enum: `ecfr_snapshot`, `ecfr_api`, `other`.
- `source_ref`: REQUIRED; SHOULD encode snapshot identity (date/version/hash). Example: `ecfr-2025-12-31-sha256:abcd...`.

## Validation rules (non-exhaustive)
- Missing any required field → invalid.
- `schema_version` mismatches → invalid.
- `doc_id` or `section_id` not matching canonical pattern or normalization → invalid.
- `text` empty or whitespace-only → invalid.
- `chunk_kind` or `source` outside allowed enums → invalid.
- Duplicate `doc_id` values → invalid.
- `parent_id` supplied but absent from corpus → invalid.
- `parent_id` that is not a canonical EAR id → invalid.
- `tokens_estimate`/`ordinal` present but not integers → invalid.

## Compatibility / extensibility
- Documents MAY include additional fields beyond those listed here; consumers MUST ignore unknown fields.

## Schema versioning
- Current version string: **`retrieval-corpus.v1`**.
- Future incompatible changes MUST bump the version (e.g., `retrieval-corpus.v2`) and update validators accordingly.
