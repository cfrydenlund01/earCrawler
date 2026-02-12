# Audit Event Requirements (Minimum Viable, Defensible)

This defines the minimum audit events required for RAG eval/operator workflows and how enforcement works.

## Required Event Types

Event schema is JSONL via the audit ledger (`event` + `payload` + chain fields):

- `run_started`
- `snapshot_selected`
- `index_selected`
- `remote_llm_policy_decision`
- query outcome: `query_answered` or `query_refused` (at least one required)

## Requirement Matrix

### A) CI eval runs (`scope=ci_eval`)

Required:

- `run_started`
- `snapshot_selected`
- `index_selected`
- `remote_llm_policy_decision`
- query outcome (`query_answered` or `query_refused`)

Enforcement:

- Set `EARCRAWLER_AUDIT_REQUIRE_EVENTS=1` to fail the run when required events are missing.

### B) Local dev runs (`scope=local_dev`)

Required:

- `run_started`
- `remote_llm_policy_decision`
- query outcome (`query_answered` or `query_refused`)

Recommended but not mandatory:

- `snapshot_selected`
- `index_selected`

### C) Operator/production runs (`scope=operator_production`)

Required:

- `run_started`
- `snapshot_selected`
- `index_selected`
- `remote_llm_policy_decision`
- query outcome (`query_answered` or `query_refused`)

## Field Expectations

Minimum payload fields by event:

- `run_started`: `run_id`, `run_kind`, `dataset_id`
- `snapshot_selected`: `run_id`, `snapshot_id`, `snapshot_sha256`, `corpus_digest`
- `index_selected`: `run_id`, `index_path`, `index_sha256`, `embedding_model`
- `remote_llm_policy_decision`: `run_id`, `trace_id`, `outcome` (`allow|deny`), `provider`, `model`, `disabled_reason`, hashed prompt/question fields only
- query outcome: `run_id`, `trace_id`, `label`, `output_ok`, refusal reason fields when applicable

Secrets must not be emitted in audit payloads (no API keys, auth headers, or raw secret material).

## Per-Run Ledger Storage

- Eval runs set run-scoped ledger IDs.
- Ledger files are stored per run under:
  - `<audit_dir>/runs/<run_id>.jsonl`
- Eval default audit dir is:
  - `dist/eval/<run_id>/audit/` (unless `EARCTL_AUDIT_DIR` is explicitly set)

## Integrity Check (Tamper Evidence)

Use:

```powershell
earctl audit verify --path <ledger.jsonl>
```

The command returns concise JSON with:

- `ok`
- `checked_entries`
- `line` (first failing line when broken)
- `reason` (for example `chain_hash_mismatch`)

This verifies hash chaining and (when configured) HMAC continuity.
