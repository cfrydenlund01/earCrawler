# Identifier Policy (Canonical citation IDs)

This document is **normative** for this repository. It defines the canonical identifier(s) used across:

- evaluation datasets (`eval/*.jsonl`)
- retrieval corpus records (`retrieval-corpus.v1`)
- KG section IRIs under the canonical namespace

Goal: prevent “citation drift” (broken citations, mismatched IRIs, and confusing evaluation outcomes) by making identifiers explicit and machine-checkable.

## 1) Canonical identifiers

### 1.1 Canonical citation identifier (MUST)

The canonical identifier for a citation is the **EAR section ID**:

- **Format:** `EAR-<section>`
- **Example:** `EAR-736.2(b)`

This is the ID that MUST be used in:

- dataset `ear_sections[]`
- dataset `expected.citations[]` (when present)
- RAG outputs’ `citations[].section_id`
- KG section IRIs (via deterministic encoding; see below)

### 1.2 Paragraph anchors (MAY; not first-class citations)

When you need a pinpoint reference within a section (for trace packs, grounding, or debugging), use a **section ID + anchor suffix**:

- **Format:** `EAR-<section>#pNNNN`
- **Example:** `EAR-736.2#p0008`

Rules:

- Anchors MUST NOT replace the base section citation ID in `ear_sections[]` / `expected.citations[]`.
- Anchors MUST be **deterministic** from a snapshot/corpus build (see §3).
- Anchor suffixes are currently reserved for paragraph chunks (the `pNNNN` form). Other suffix shapes are reserved for future use.

## 2) Normalization rules (MUST)

Any input that is intended to be an EAR section ID MUST be normalized to the canonical form before being stored or compared.

Canonicalization rules:

- Trim whitespace (including non‑breaking spaces).
- Strip leading `§`.
- Allow and remove a leading `15 CFR` prefix.
- Allow `EAR-...` or `EAR ...` prefixes; normalize to `EAR-`.
- Remove internal spaces.
- Lowercase the section body (subsection letters, etc.).
- Remove trailing periods.

Source of truth implementation:

- `earCrawler/rag/corpus_contract.py` → `normalize_ear_section_id()` (canonical section IDs)
- `earCrawler/rag/corpus_contract.py` → `normalize_ear_doc_id()` (section IDs + `#pNNNN` anchors)

## 3) Deterministic paragraph anchor mapping (MUST if used)

Paragraph anchors MUST be computable from the snapshot/corpus deterministically (no manual numbering).

Current repository rule (retrieval-corpus.v1):

- Build paragraph chunks by splitting oversized section/subsection text on blank lines (with deterministic fallbacks).
- Within a given container (e.g., `EAR-736.2`), assign paragraph anchors in source order:
  - `#p0001`, `#p0002`, …, `#pNNNN`
- The paragraph number corresponds to the chunk’s `ordinal` within its parent container.

Reference implementation:

- `earCrawler/rag/chunking.py` → paragraph chunk emission uses `#p{idx:04d}`.

## 4) Machine-checkable validation (MUST)

### 4.1 Canonical section ID regex

The canonical section ID MUST match this pattern (case-sensitive; subsection letters must be lowercase):

```
^EAR-\d{3}(?:\.\d+[a-z0-9]*)+(?:\([a-z0-9]+\))*$
```

### 4.2 Canonical anchored ID regex (paragraph chunks)

Anchored paragraph IDs MUST match:

```
^EAR-\d{3}(?:\.\d+[a-z0-9]*)+(?:\([a-z0-9]+\))*#p\d{4}$
```

### 4.3 Resolution rule (MUST)

A canonical section citation ID (`EAR-...`) MUST resolve to exactly one corpus document:

- There MUST be exactly one corpus record whose `doc_id` equals the citation ID (no `#...` suffix).
- Additional child chunks MAY exist under the same section via anchored `doc_id` values (e.g. `EAR-736.2#p0008`) and MUST carry `section_id` equal to the base citation ID.

## 5) KG IRI mapping (MUST)

KG section nodes MUST use the canonical IRI strategy defined in:

- `docs/kg_boundary_and_iri_strategy.md`

In particular:

- Section IRI format: `https://ear.example.org/resource/ear/section/<encoded_section_id>`
- `<encoded_section_id>` is the canonical section ID RFC3986 percent-encoded.
