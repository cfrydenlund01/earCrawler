# Model Training Input Contract

Status: planning-only document for Phase 5 Task 5.2. This document defines the
training-input contract for future model work. It does not make local training,
checkpoint handling, or model serving part of the supported runtime today.

## Goal

Create a deterministic training package for the production-intended 7B model
that is anchored to the supported evidence path already validated in this repo.

The contract is designed to keep model training tied to:

- an approved offline eCFR snapshot
- the deterministic retrieval corpus derived from that snapshot
- explicit separation between production training data, eval data, and future
  benchmark data

## Scope

This contract applies to the first production-oriented fine-tuning pass planned
in Task 5.3 for `Qwen/Qwen2.5-7B-Instruct`.

It is intentionally narrow:

- source text comes from the supported EAR retrieval path
- examples are instruction-tuning examples for evidence-grounded answering or
  refusal
- training inputs must be reproducible from named manifests and digests

## Authoritative input sources

All production training examples MUST be traceable to the following sources:

1. An approved offline snapshot manifest and payload:
   - `snapshots/offline/<snapshot_id>/manifest.json`
   - `snapshots/offline/<snapshot_id>/snapshot.jsonl`
   - Contract reference: `docs/offline_snapshot_spec.md`
2. A retrieval corpus built deterministically from that snapshot:
   - schema: `retrieval-corpus.v1`
   - typical output path: `data/faiss/retrieval_corpus.jsonl`
   - paired FAISS metadata path: `data/faiss/index.meta.json`
   - contract reference: `retrieval_corpus_contract.md`
3. A recorded base-model selection:
   - `Qwen/Qwen2.5-7B-Instruct`
   - reference: `docs/model_training_surface_adr.md`

## Non-authoritative and excluded sources

The following are not training-authoritative for Task 5.2:

- `data/experimental/retrieval_corpus_6_record_fr_sections.jsonl` (small
  derivative scratch corpus for FR-section rebuild experiments)
- `eval/*.jsonl`
- `dist/eval/**`
- `tests/fixtures/**`
- `tests/golden/**`
- proposal or research notes under `Research/` or `docs/proposal/`
- benchmark planning assets before Phase 6

These assets may inform review or analysis, but they MUST NOT be mixed into the
production training package.

## KG role

KG artifacts are optional metadata for Task 5.2, not the primary source of
training truth.

- A local KG is NOT required to generate the first-pass training examples.
- If present, `kg/.kgstate/manifest.json` MAY be recorded in training metadata
  for provenance alignment.
- KG-derived nodes, paths, or search behavior MUST NOT become a hidden
  prerequisite for producing the base training package while KG-backed runtime
  behavior remains quarantined.

This keeps the first training package aligned to the supported text evidence
path rather than to a still-evolving KG runtime surface.

## Training package layout

The future training packer for Task 5.3 should emit a deterministic directory:

- `dist/training/<run_id>/manifest.json`
- `dist/training/<run_id>/examples.jsonl`

The `run_id` SHOULD encode the snapshot identity and package version, for
example:

- `qwen25-7b-ear-2026-03-11-snapshot-2026-02-28-v1`

## Example schema

Training examples MUST be stored as JSONL. One JSON object per line.

Required fields:

- `schema_version`: MUST equal `instruction-tuning.v1`
- `example_id`: stable unique identifier
- `split`: MUST equal `train`
- `task`: one of `answer`, `refusal`
- `base_model`: MUST equal `Qwen/Qwen2.5-7B-Instruct` for the first pass
- `question`: natural-language user question
- `messages`: ordered chat messages used for supervised fine-tuning
- `evidence`: array of supporting retrieval documents
- `target`: structured expected assistant behavior
- `provenance`: source snapshot and corpus identity metadata

Required `evidence[]` fields:

- `doc_id`
- `section_id`
- `source_ref`
- `quote`

Required `target` fields:

- `answer`
- `citations`
- `refusal`

Required `provenance` fields:

- `snapshot_id`
- `snapshot_sha256`
- `retrieval_corpus_digest`

Example shape:

```json
{
  "schema_version": "instruction-tuning.v1",
  "example_id": "ear-answer-736_2b_0001",
  "split": "train",
  "task": "answer",
  "base_model": "Qwen/Qwen2.5-7B-Instruct",
  "question": "When is a license required under 15 CFR 736.2(b)?",
  "messages": [
    {
      "role": "system",
      "content": "Answer only from cited EAR evidence. Refuse when evidence is insufficient."
    },
    {
      "role": "user",
      "content": "When is a license required under 15 CFR 736.2(b)?"
    },
    {
      "role": "assistant",
      "content": "A license requirement depends on the specific general prohibition that applies. See 15 CFR 736.2(b)."
    }
  ],
  "evidence": [
    {
      "doc_id": "EAR-736.2(b)",
      "section_id": "EAR-736.2(b)",
      "source_ref": "ecfr-2026-02-28-sha256:abcd",
      "quote": "General Prohibitions describe when a license is required."
    }
  ],
  "target": {
    "answer": "A license requirement depends on the applicable General Prohibition in 15 CFR 736.2(b).",
    "citations": ["EAR-736.2(b)"],
    "refusal": false
  },
  "provenance": {
    "snapshot_id": "ecfr-title15-2026-02-28",
    "snapshot_sha256": "abcd",
    "retrieval_corpus_digest": "1234"
  }
}
```

## Refusal examples

Refusal examples are first-class training items and must use the same evidence
and provenance rules.

Rules:

- `task` = `refusal`
- `target.refusal` = `true`
- `target.answer` must explain that the answer cannot be given from the
  provided evidence or is outside scope
- `target.citations` may be empty when refusal is due to insufficient evidence

## Deterministic regeneration rules

The training package is deterministic only if all of the following are pinned:

1. Base model ID
2. Offline snapshot manifest path
3. Offline snapshot payload hash
4. Retrieval corpus schema version
5. Retrieval corpus digest
6. Example-generation config version
7. Output sort order by `example_id`

Regeneration procedure for Tasks 5.2 and 5.3:

1. Validate the offline snapshot.
2. Build the retrieval corpus from the approved snapshot.
3. Record the resulting `snapshot_id`, `snapshot_sha256`, and
   `retrieval_corpus_digest`.
4. Generate `examples.jsonl` using only approved training-authoritative inputs.
5. Sort examples by `example_id` before writing.
6. Write a `manifest.json` that records all pinned inputs and output hashes.

If any pinned input changes, the training package version MUST change.

## Runner preflight enforcement

`scripts/training/run_phase5_finetune.py` performs a contract preflight before
writing artifacts or launching training:

1. The configured `--retrieval-corpus` path must match
   `authoritative_sources.retrieval_corpus_jsonl` from
   `config/training_input_contract.example.json`.
2. The configured `--index-meta` path must match
   `authoritative_sources.faiss_index_meta_json` when that field is present.
3. The configured `--snapshot-manifest` path must match
   `authoritative_sources.offline_snapshot_manifest` when that field is
   present, and `snapshot_id` / `snapshot_sha256` must match the manifest.
4. The FAISS `snapshot.snapshot_id` / `snapshot.snapshot_sha256` values must
   match the approved snapshot manifest when FAISS snapshot metadata is present.
5. The retrieval corpus SHA-256 and non-empty JSONL record count must match
   `corpus_digest` and `doc_count` from `data/faiss/index.meta.json`.
6. When `require_qlora_4bit=true`, `use_4bit=true` is mandatory before
   packaging/training can proceed.

If any check fails, the run exits before packaging or training.

## Data separation policy

The repository now uses this separation rule for future model work:

- Production training data: generated from approved offline snapshot text and
  the derived retrieval corpus only.
- Eval data: all current files under `eval/` remain holdout-only and are never
  copied into `examples.jsonl`.
- Future benchmark data: deferred until Phase 6 and must live in a separately
  named benchmark package or manifest. It must not be merged into either
  training or eval by default.

## Minimal manifest requirements

The future `dist/training/<run_id>/manifest.json` MUST record at least:

- `manifest_version`
- `base_model`
- `snapshot_manifest_path`
- `snapshot_id`
- `snapshot_sha256`
- `retrieval_corpus_path`
- `retrieval_corpus_digest`
- `example_schema_version`
- `example_count`
- `examples_sha256`
- `excluded_globs`
- `generated_at`

## Task 5.3 implementation references

Task 5.3 implementation now uses:

- `scripts/training/run_phase5_finetune.py` (package + train + metadata)
- `scripts/training/run_phase5_finetune.ps1` (repeatable Windows wrapper)
- `scripts/training/inference_smoke.py` (standalone adapter load smoke)
- `docs/model_training_first_pass.md` (operator/developer runbook for the pass)
- `config/training_first_pass.example.json` (repeatable run-config template)

The script-generated package and metadata layout is:

- `dist/training/<run_id>/examples.jsonl`
- `dist/training/<run_id>/manifest.json`
- `dist/training/<run_id>/run_config.json`
- `dist/training/<run_id>/run_metadata.json`
- `dist/training/<run_id>/adapter/`
- `dist/training/<run_id>/inference_smoke.json`

## Current conclusion

Task 5.2 is complete when the repo has one clear answer to these questions:

- What text is the model trained on?
  - Approved eCFR snapshot text, via the retrieval corpus.
- Is a local KG required before training?
  - No, not for the first pass.
- Can eval or benchmark data leak into training?
  - No; they are explicitly excluded by contract.
