# Versioned Artifact Contract Strategy

Status: implementation-ready design for review pass 7 step 6.

## Goal

Define one practical contract strategy for the core artifacts that already exist in the supported path:

- corpus records
- KG emitter inputs and KG snapshot metadata
- retrieval documents
- evaluation artifacts

This design is intentionally incremental. It does not replace the current supported architecture, and it does not promote quarantined KG-backed runtime behavior. It adds explicit contract ownership, versioning, validation, and migration rules so contract drift becomes detectable before it reaches release evidence.

## Why this is needed now

The pass 7 NSF entity drift is not an isolated bug. It exposed a broader gap:

- corpus builders emitted a real structure
- the KG emitter accepted a different assumed structure
- tests still encoded the legacy assumption

The repo already has partial contract discipline:

- retrieval documents use `retrieval-corpus.v1`
- offline snapshots use `offline-snapshot.v1`
- some training and run manifests already carry `schema_version` or `manifest_version`
- KG state already has a manifest-driven snapshot identity

What is missing is a single policy that defines:

- which module owns each artifact contract
- where version checks must happen
- when a change is additive vs breaking
- how downstream consumers declare the versions they accept

## Design principles

1. Supported-path first. Contracts must first stabilize the Windows single-host deterministic path already treated as credible.
2. Artifact boundaries over module boundaries. Versions attach to files and payload shapes, not to vague subsystems.
3. One canonical writer, many strict readers. Each artifact family has a single normative producer contract and strict validation at every boundary.
4. Additive evolution within a major line. New optional fields can stay within `v1`; shape or semantic meaning changes require `v2`.
5. Machine-checked compatibility. Consumers must declare accepted versions and fail clearly on unsupported ones.
6. Provenance must chain across artifacts. Each downstream artifact records the upstream artifact ids, digests, and schema versions it was built from.

## Contract families

| Artifact family | Canonical artifact | Current state | Proposed canonical version id | Primary owner |
| --- | --- | --- | --- | --- |
| Corpus records | `data/*_corpus.jsonl` | implicit, source-specific, partly normalized | `corpus-record.v1` envelope plus source payload version | `earCrawler/corpus/` |
| KG emitter input | normalized corpus-to-KG handoff | implicit; drift already occurred | `kg-input.v1` | `earCrawler/kg/` with corpus co-ownership |
| KG snapshot metadata | `kg/.kgstate/manifest.json` and emitted TTL dataset metadata | partly versioned by manifest practice | `kg-manifest.v1` | `earCrawler/kg/` |
| Retrieval documents | `retrieval_corpus.jsonl` | explicit today | `retrieval-corpus.v1` | `earCrawler/rag/` |
| Eval dataset manifest | `eval/manifest.json` | loosely structured | `eval-manifest.v1` | `eval/` plus `scripts/eval/` |
| Eval dataset items | `eval/*.jsonl` | loosely structured with validator behavior | `eval-item.v1` | `eval/` plus `scripts/eval/` |
| Eval run artifacts | `dist/eval/**`, trace packs, summaries | partially versioned by convention | `eval-run.v1` and `trace-pack.v1` | `scripts/eval/` |

## Common contract envelope

Every versioned artifact family should use the same minimum envelope, even when payload fields differ.

Required top-level fields:

- `schema_version` for record-like JSON/JSONL objects
- `manifest_version` for aggregate manifests
- `artifact_family`
- `produced_by`
- `generated_at` for generated outputs

Required provenance fields for downstream artifacts:

- `input_artifacts`: array of `{artifact_family, schema_version, path_or_id, sha256}`
- `source_snapshot` when a snapshot exists
- `contract_owner`

Rules:

- `schema_version` and `manifest_version` are opaque strings such as `retrieval-corpus.v1`.
- The family prefix is stable even if ownership changes.
- A downstream artifact must record the exact upstream versions it consumed, not just its own version.

## 1. Corpus record strategy

### Canonical model

Introduce a shared corpus contract module:

- `earCrawler/contracts/corpus_record.py`

It should define:

- `CORPUS_RECORD_VERSION = "corpus-record.v1"`
- a typed normalized record model used after source-specific parsing
- a source payload substructure for source-specific fields

Recommended normalized fields:

- `schema_version`
- `record_id`
- `source`
- `source_record_id`
- `title` optional
- `text`
- `section`
- `date`
- `source_url`
- `content_sha256`
- `entities`
- `provenance`
- `source_payload_version`

Rules:

- `entities` must use one shared typed entity shape across EAR and NSF normalized records.
- Source-specific oddities must stay inside `provenance` or `source_payload`, not leak into downstream expectations.
- Builders may emit additional optional fields in `v1`, but they must not change the meaning or type of existing fields.

### Ownership boundary

- Source loaders own raw parse structures.
- `earCrawler/corpus/` owns normalized `corpus-record.v1`.
- No downstream package may parse source loader output directly.

### Validation points

- immediately after normalization in corpus build
- during `corpus validate`
- before any downstream conversion step reads `*_corpus.jsonl`

## 2. KG input strategy

### Canonical model

The KG layer should stop reading ad hoc corpus dicts. Instead it should consume a dedicated normalized handoff contract:

- `earCrawler/contracts/kg_input.py`
- `KG_INPUT_VERSION = "kg-input.v1"`

This contract is not a new file format by default. It is the required in-memory and file-level semantic shape that emitters accept after loading corpus records.

Recommended fields:

- `schema_version`
- `record_id`
- `source`
- `text`
- `section`
- `issued_date`
- `source_reference`
- `entities`
- `lineage`

Rules:

- `kg-input.v1` may be a strict subset plus renaming of `corpus-record.v1`.
- The normalization function from corpus records to KG inputs must live in one shared module, not inside per-emitter code.
- Emitters must reject legacy shapes instead of silently iterating them.

### Ownership boundary

- corpus owns raw corpus files
- the corpus-to-KG adapter owns the transformation into `kg-input.v1`
- KG emitters own RDF/Turtle generation only

This boundary is the key protection against repeat drift.

### Validation points

- adapter validation before emission
- emitter preflight asserting accepted `schema_version`
- supported-path integration test from real corpus build output into KG emission

### How this would have prevented the NSF drift

If the current repo had required `kg-input.v1`:

- the corpus builder would have emitted typed `entities`
- the corpus-to-KG adapter would have normalized that shape once
- `emit_nsf.py` would only accept `kg-input.v1`
- tests would validate the adapter and emitter against the same typed structure

The mismatch would have failed at the adapter boundary instead of silently dropping entity names in emitted TTL.

## 3. KG snapshot metadata strategy

The RDF triples themselves are already governed by namespace and IRI rules in the KG docs. The missing piece is a stricter versioned manifest for KG outputs.

Canonical manifest:

- `kg/.kgstate/manifest.json`
- `manifest_version = "kg-manifest.v1"`

Required fields:

- `manifest_version`
- `graph_iri`
- `digest`
- `artifact_paths`
- `input_artifacts`
- `ontology_namespace_version`
- `kg_input_version`
- `emitter_version`

Rules:

- TTL emission does not need a new `schema_version` field inside every triple file.
- The manifest is the versioned contract for the emitted KG snapshot as a whole.
- Any release gate, bundle, or eval artifact that depends on the KG must record `digest` plus `manifest_version`.

## 4. Retrieval document strategy

The retrieval layer is ahead of the rest of the repo and should become the model for the other families.

Current baseline to preserve:

- `retrieval-corpus.v1`
- strict validation
- canonical identifiers
- digest-based downstream metadata in index manifests

Required refinements:

- keep `retrieval-corpus.v1` as the canonical retrieval document contract until a breaking need appears
- add an explicit contract note that retrieval builders may consume `corpus-record.v1` but must not consume source-specific loader output
- require index metadata to record both:
  - `corpus_schema_version`
  - `corpus_digest`
- require eval run artifacts to record the retrieval corpus version and digest they used

Breaking-change rule:

- changes to retrieval doc identity, required fields, temporal semantics, or citation semantics require `retrieval-corpus.v2`
- additive optional metadata remains in `v1`

## 5. Evaluation artifact strategy

Evaluation currently spans three distinct contract surfaces and they should be versioned separately.

### Eval manifest

Canonical version:

- `eval-manifest.v1`

Required fields:

- `manifest_version`
- `datasets`
- per-dataset `id`, `file`, `item_schema_version`

### Eval dataset items

Canonical version:

- `eval-item.v1`

Required fields:

- `schema_version`
- `id`
- `task`
- `question`
- `ground_truth`
- evidence/reference fields already required by validators

Rules:

- eval items should not depend on undocumented retrieval or KG runtime internals
- references to citations, KG nodes, and sections must follow the existing identifier policy

### Eval run outputs

Canonical versions:

- summary/report JSON: `eval-run.v1`
- trace pack JSON: `trace-pack.v1`

Required provenance:

- `eval_manifest_version`
- `eval_item_version`
- `retrieval_corpus_version`
- `retrieval_corpus_digest`
- `kg_manifest_version` and `kg_digest` when KG is involved
- snapshot ids and hashes when snapshot-backed

This makes benchmark and release evidence comparable across runs.

## Version semantics

Use the following compatibility rules for all families.

### Allowed without version bump

- adding optional fields
- tightening documentation
- adding validators for previously undocumented invalid states, if all committed canonical artifacts already pass

### Requires new major version

- renaming fields
- changing field types
- changing cardinality
- changing semantic meaning of an existing field
- changing identifier canonicalization rules
- changing provenance requirements in ways that break old readers

### Reader policy

Every consumer must do one of these explicitly:

- accept exactly one version
- accept a declared allowlist such as `{"corpus-record.v1"}`

Readers must fail with a direct error message on unsupported versions. Silent fallback is not allowed on supported paths.

## Validation and enforcement plan

Validation should happen at four layers.

### Layer 1: contract modules

Each family gets a small contract module with:

- version constant
- typed model or validator
- normalization helpers
- error formatter

### Layer 2: CLI and build boundaries

Commands that produce or consume artifacts must validate at entry and exit:

- `corpus build` validates normalized records before writing
- `corpus validate` validates committed corpus files against `corpus-record.v1`
- KG emit validates `kg-input.v1`
- retrieval builders validate `retrieval-corpus.v1`
- eval dataset validators validate `eval-manifest.v1` and `eval-item.v1`

### Layer 3: integration tests

Required supported-path regression coverage:

- real corpus build output -> KG adapter -> KG emit
- snapshot/retrieval corpus -> index metadata
- eval manifest + dataset -> eval run summary + trace pack provenance

### Layer 4: CI release gates

The supported CI path should fail when:

- an artifact claims an unsupported schema version
- a downstream manifest omits required upstream provenance
- a supported-path integration test proves a boundary contract broke

## Migration rules

The repo does not need a flag day migration. Use staged adoption.

### Rule 1: version before refactor

Before changing a boundary, define its contract module and validators first.

### Rule 2: dual-read, single-write

During migration windows:

- writers emit only the new canonical version
- readers may temporarily accept both the current legacy shape and the new version
- this dual-read logic must have a documented removal point

### Rule 3: artifact rebuild over hand-edit

For generated artifacts:

- rebuild from authoritative inputs
- do not hand-edit JSONL, manifests, or TTL to satisfy a new version

### Rule 4: migration notes are mandatory for breaking versions

Any future `v2` must ship with:

- migration note in `docs/`
- compatibility window statement
- updated validators and fixtures

## Recommended implementation sequence after current P0 fixes

This sequence assumes pass 7 steps 2 through 5 are already complete or landing now.

1. Add `earCrawler/contracts/` with shared version constants and validator helpers.
2. Land `corpus-record.v1` as the normalized corpus contract without changing supported file paths.
3. Add a shared typed entity schema used by corpus normalization and KG input normalization.
4. Add `kg-input.v1` adapter functions and make NSF KG emission consume only that adapter output.
5. Version `kg/.kgstate/manifest.json` explicitly as `kg-manifest.v1`.
6. Add explicit `eval-manifest.v1` and `eval-item.v1` validators, then stamp committed eval assets.
7. Add `eval-run.v1` and `trace-pack.v1` provenance fields to report outputs.
8. Promote CI checks that assert version presence and upstream provenance continuity across the supported path.

## Concrete first file/module changes

The smallest useful initial implementation slice is:

- add `earCrawler/contracts/__init__.py`
- add `earCrawler/contracts/corpus_record.py`
- add `earCrawler/contracts/entities.py`
- add `earCrawler/contracts/kg_input.py`
- update corpus builder and validator to stamp `corpus-record.v1`
- update KG emitters to consume normalized `kg-input.v1`
- add eval validators for manifest/item version fields

This is enough to close the gap that caused the NSF defect and establish the reusable pattern for the other artifact families.

## Non-goals

This design does not:

- make KG-backed search supported
- redesign the service API contract
- introduce multi-instance coordination
- require a new storage engine
- require greenfield schema tooling such as Avro or Protobuf

The repo is already JSON/JSONL and manifest oriented. The contract strategy should stay there unless a later real requirement proves otherwise.

## Final recommendation

Treat versioned artifact contracts as a supported-path safety mechanism, not as documentation polish.

The immediate priority is to formalize:

- `corpus-record.v1`
- `kg-input.v1`
- `kg-manifest.v1`
- `eval-manifest.v1`
- `eval-item.v1`
- `eval-run.v1`

while preserving the existing `retrieval-corpus.v1` baseline.

That gives the project one coherent rule: every important artifact crossing a subsystem boundary has an owner, a version, a validator, and upstream provenance. That is the practical change most likely to prevent another silent cross-boundary drift like the NSF entity loss.
