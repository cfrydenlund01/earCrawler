# KG boundary and canonical IRI strategy

This document is **normative** for this repository. It defines the canonical KG boundary, the canonical namespaces, and the deterministic IRI strategy that MUST be used for new outputs.

## 1) Canonical namespaces

### 1.1 Canonical (MUST use for new outputs)

- **Schema / ontology terms (classes + predicates)**: `https://ear.example.org/schema#`
- **Resources (sections, paragraphs, policy nodes, provenance resources)**: `https://ear.example.org/resource/`
- **Named graphs / snapshots**: `https://ear.example.org/graph/`
- **Entities (CSL / Trade.gov / reconciled entity nodes)**: `https://ear.example.org/entity/`
- **EAR Parts**: `https://ear.example.org/part/`
- **Anchors**: `https://ear.example.org/anchor/`
- **Policy hints**: `https://ear.example.org/policyHint/`

### 1.2 Legacy namespaces (MUST NOT be emitted by new code)

These namespaces exist in older fixtures/snapshots and are considered **legacy**:

- `https://example.org/ear#`
- `https://example.org/entity#`
- `http://example.org/ear/`

New code MUST emit canonical namespaces only. Legacy IRIs MAY appear in stored snapshots; consumers SHOULD canonicalize them via the explicit alias mapping described in the migration plan.

## 2) KG boundary

### 2.1 “Inside KG” (MUST be canonical IRIs)

The following live **inside** the KG and MUST use canonical IRIs:

- Ontology/schema terms under `https://ear.example.org/schema#`
- EAR sections and paragraphs emitted from corpora (including deterministic IDs)
- Entities, parts, mentions, anchors, policy hints
- Provenance resources associated with ingestion (agents, requests, activities) when represented as nodes

### 2.2 “External references” (MUST NOT become canonical IDs)

The following are **external references** and MUST NOT be used as canonical resource identifiers:

- Source URLs (Federal Register, Trade.gov, eCFR, etc.)
- Third-party IDs (Federal Register document IDs, external dataset IDs)

External identifiers MUST be represented as:

- IRIs **only** when they are true web identifiers (e.g. `dct:source <https://...>`), and/or
- literals for non-URLs, and/or
- `owl:sameAs` links when explicitly equating an internal node with an external identifier

## 3) Named graph versioning and identification

### 3.1 Graph IRIs (MUST be deterministic)

- The canonical KG snapshot named graph IRI MUST be:
  - `https://ear.example.org/graph/kg/<snapshot_digest>`
- `<snapshot_digest>` MUST be the hex digest recorded at `kg/.kgstate/manifest.json` under `digest`.

`https://ear.example.org/graph/main` MAY be used as a moving pointer for “latest”, but MUST NOT be used as the immutable identity of a snapshot.

### 3.2 Manifest source of truth (MUST)

- Snapshot metadata is stored at `kg/.kgstate/manifest.json`.
- The `digest` field is the source of truth for snapshot identity.
- Any downstream artifacts (evaluation dataset manifests, export bundles) SHOULD record the snapshot digest they are aligned to.

### 3.3 SPARQL targeting rules (SHOULD)

- Queries that require snapshot stability SHOULD target a snapshot graph IRI explicitly via `GRAPH <https://ear.example.org/graph/kg/<digest>> { ... }`.
- Interactive/service queries MAY use the dataset’s default graph when the dataset is explicitly configured to represent “main”.

## 4) Grounding/citation alignment rule

### 4.1 Canonical section identifier (MUST align)

The canonical section identifier string used in:

- retrieval citations (e.g. `EAR-736.2(b)`)
- evaluation references (`ear_sections`)
- KG section node IRIs

MUST be identical up to a deterministic encoding rule.

### 4.2 Section IRI format (MUST)

The canonical section node IRI MUST be:

- `https://ear.example.org/resource/ear/section/<encoded_section_id>`

Where:

- `<encoded_section_id>` is the canonical section ID (e.g. `EAR-736.2(b)`) encoded with RFC3986 percent-encoding for any character outside unreserved `[A-Za-z0-9-._~_]`.

Examples:

- `EAR-736.2(b)` → `https://ear.example.org/resource/ear/section/EAR-736.2%28b%29`
- `EAR-740.9(a)(2)` → `https://ear.example.org/resource/ear/section/EAR-740.9%28a%29%282%29`

