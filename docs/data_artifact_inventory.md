# Data Artifact Inventory

Prepared: March 18, 2026

Use this page when you need to know which repository artifacts are the source
of truth versus derived outputs or experimental scratch data.

Artifact classes:

- `Authoritative`: canonical input or contract artifact for an active workflow.
- `Derived`: reproducible artifact built from authoritative inputs and used by
  active workflows, but not the root source of truth.
- `Experimental`: scratch, optional, or quarantined artifact that must not be
  mistaken for the supported baseline.
- `Generated`: run output, evidence bundle, or packaging output; never edit as
  a source input.
- `Archival`: retained historical artifact for reference only.

## Core inputs and contracts

| Path or pattern | Class | Workflows | Notes |
| --- | --- | --- | --- |
| `snapshots/offline/<snapshot_id>/manifest.json` | Authoritative | Offline snapshot validation, corpus rebuild, training provenance | Approved snapshot manifest tracked in git. |
| `snapshots/offline/<snapshot_id>/snapshot.jsonl` | Authoritative | Offline snapshot validation, corpus rebuild, training provenance | External payload paired with the tracked manifest; local working copy only. |
| `data/faiss/retrieval_corpus.jsonl` | Authoritative | Supported retrieval corpus contract, retriever setup, training preflight | Canonical retrieval corpus path for current retrieval and training workflows. |
| `data/faiss/index.meta.json` | Authoritative | Retrieval runtime wiring, training preflight, baseline provenance | Canonical sidecar for corpus digest, doc count, model, and build metadata. |
| `eval/manifest.json` | Authoritative | Eval selection, dataset validation, baseline FR coverage, trace provenance | Dataset index plus pinned KG-state digest and curated references. |
| `eval/schema.json` | Authoritative | Eval dataset validation | Schema contract for `eval/*.jsonl` items. |
| `config/training_input_contract.example.json` | Authoritative | Training preflight, training docs | Planning-only contract, but it is the current source of truth for authoritative training inputs. |

## Runtime, eval, and KG-support artifacts

| Path or pattern | Class | Workflows | Notes |
| --- | --- | --- | --- |
| `data/faiss/index.faiss` | Derived | Optional FAISS-backed retrieval, baseline provenance, index rebuild verification | Built from the authoritative retrieval corpus; treat `index.meta.json` as the contract sidecar. |
| `data/fr_sections.jsonl` | Derived | FR coverage gate, coverage reporting | Maintained coverage corpus used by baseline verification; not training-authoritative. |
| `kg/.kgstate/manifest.json` | Derived | Eval manifest pinning, optional training metadata | KG-state digest used as a provenance checkpoint, not as the root text source. |
| `data/kg_expansion.json` | Experimental | Optional KG expansion experiments | Quarantined runtime support; not baseline retrieval truth. |
| `eval/*.jsonl` | Authoritative | Held-out evaluation and golden gates | Holdout datasets only; never mix into training examples. |

## Experimental and scratch data

| Path or pattern | Class | Workflows | Notes |
| --- | --- | --- | --- |
| `data/experimental/retrieval_corpus_6_record_fr_sections.jsonl` | Experimental | Local FR-section rebuild experiments only | Intentionally not the authoritative retrieval corpus. |
| `Research/` notes that embed copied metrics or ad hoc result snippets | Archival | Review history, planning | Informative only; not an active runtime or training contract. |

## Generated run outputs

| Path or pattern | Class | Workflows | Notes |
| --- | --- | --- | --- |
| `dist/corpus/<snapshot_id>/retrieval_corpus.jsonl` | Generated | Deterministic corpus rebuild verification | Rebuilt output for a named snapshot; compare against the authoritative contract, do not edit by hand. |
| `dist/corpus/<snapshot_id>/build_log.json` | Generated | Corpus provenance and determinism checks | Records corpus digest, snapshot provenance, and smoke-check status. |
| `dist/index/<snapshot_id>/index.faiss` | Generated | FAISS rebuild verification | Rebuilt index artifact from `dist/corpus/<snapshot_id>/retrieval_corpus.jsonl`. |
| `dist/index/<snapshot_id>/index.meta.json` | Generated | FAISS rebuild verification | Rebuilt sidecar for the generated index; useful evidence, not the checked-in contract file. |
| `dist/index/<snapshot_id>/index_build_log.json` | Generated | FAISS rebuild verification | Records smoke query and wiring checks for the rebuilt index. |
| `dist/baseline/<timestamp>/` | Generated | Baseline evidence bundles | Contains logs, FR coverage outputs, golden-gate results, and baseline summary metadata. |
| `dist/eval/` | Generated | Eval runs and comparison reports | Per-run evaluation outputs, evidence reports, and markdown summaries. |
| `dist/training/<run_id>/manifest.json` | Generated | Optional training-package review | Run-specific manifest for a named training candidate. |
| `dist/training/<run_id>/examples.jsonl` | Generated | Optional training-package review | Instruction-tuning examples built from the authoritative snapshot/corpus contract. |
| `dist/training/<run_id>/run_config.json` | Generated | Optional training-package review | Concrete run configuration captured for reproducibility. |
| `dist/training/<run_id>/run_metadata.json` | Generated | Optional training-package review | Run outcome, metrics, and artifact metadata. |
| `dist/training/<run_id>/adapter/` | Generated | Optional local-adapter runtime candidate | Candidate adapter artifact; optional until promoted by evidence. |
| `dist/training/<run_id>/inference_smoke.json` | Generated | Optional training/runtime smoke evidence | Smoke-test result for the named adapter run. |
| `dist/training/<run_id>/release_evidence_manifest.json` | Generated | Optional local-adapter release review | Decision manifest produced from the release-evidence contract; records hashes, thresholds, and review outcome for one adapter candidate. |
| `dist/benchmarks/` | Generated | Optional benchmark evidence | Benchmark outputs and manifests; evidence only, never input truth. |

## Practical rules

1. Treat `snapshots/offline/<snapshot_id>/manifest.json` plus
   `data/faiss/retrieval_corpus.jsonl` and `data/faiss/index.meta.json` as the
   current text-and-retrieval truth chain.
2. Treat `eval/manifest.json`, `eval/schema.json`, and `eval/*.jsonl` as the
   holdout evaluation truth chain.
3. Treat anything under `dist/` as generated evidence for a specific run, not
   as a maintained source artifact.
4. Do not use `data/experimental/` or quarantined KG artifacts as defaults for
   supported runtime or training work.
5. When a workflow needs provenance, prefer the manifest/sidecar file over
   inferring truth from filenames alone.
