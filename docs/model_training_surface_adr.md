# Model Training Surface ADR

Prepared: March 9, 2026

## Problem

Review pass 5 identified ambiguity between the runtime the repository actually
supports and model-training capability implied by scaffolding references such as
`agent/`, `models/legalbert/`, and `quant/`.

In the current checkout:

- `agent/` is absent
- `models/legalbert/` is absent
- the only concrete training-adjacent Python surface was `earCrawler.quant`, a
  placeholder dataclass used only by a unit test

The shipped operator surface is the CLI, corpus pipeline, evaluation harness,
and `service.api_server`. The repository does not include a real training stack:
no checkpoint lifecycle, no trainer configuration, no reproducible experiment
runner, no training datasets or artifact contracts, and no runbook for
operating fine-tuned models.

## Decision

This repository does not currently support model training, fine-tuning,
quantization workflows, or agent-runtime experimentation as a first-class
product or research surface.

To make that explicit:

- remove placeholder Python scaffolding that implies training capability
- keep optional GPU dependencies scoped to retrieval/indexing experiments only
- treat proposal and `Research/` assets as documentation helpers, not runtime
  commitments
- require a separate design/operations decision before introducing any future
  training or agent stack

## Consequences

- `earCrawler.quant` is removed rather than promoted
- absent historical surfaces such as `agent/` and `models/legalbert/` remain
  intentionally unsupported
- operators should not infer that local model checkpoints, quantized weights, or
  fine-tuning workflows are part of the supported release story
- future training work must arrive with explicit scope, packaging, evaluation,
  security, and runbook support instead of placeholder modules

## Phase 5.1 Selection Record

On March 11, 2026, Task 5.1 selected one production-intended 7B base model for
future training work: `Qwen/Qwen2.5-7B-Instruct`.

At the time of Task 5.1, this decision did not change the current support
boundary. The selection existed so later Phase 5 work could proceed from one
explicit base-model assumption instead of revisiting model choice while the
training contract was being built. Task 5.4 later added one narrowly gated
runtime path for serving a Task 5.3 adapter, but not a general local
model-serving stack.

The planning-only config record lives at
`config/training_model_selection.example.env` and currently captures:

- Hugging Face model ID: `Qwen/Qwen2.5-7B-Instruct`
- Model family: `Qwen2.5`
- Parameter class: `7B`
- Official upstream repository: `https://github.com/QwenLM/Qwen`

Until Tasks 5.2 through 5.4 are complete, this selection should be read as a
future training target only, not as an active runtime dependency or operator
requirement.

## Phase 5.2 Training Contract Record

On March 11, 2026, Task 5.2 defined the planning-only training-input contract
for the first production-oriented fine-tuning pass.

That contract is documented in:

- `docs/model_training_contract.md`
- `config/training_input_contract.example.json`

The key decisions are:

- authoritative training text comes from approved offline eCFR snapshots and
  the derived `retrieval-corpus.v1` corpus
- eval datasets under `eval/` remain holdout-only and are excluded from
  training-package generation
- future benchmark data remains deferred and must stay separate from both
  training and eval packages
- a local KG is optional provenance metadata, not a hard prerequisite for the
  first fine-tuning pass

## Phase 5.3 First Fine-Tuning Pass Record

On March 11, 2026, Task 5.3 added a repeatable first-pass fine-tuning workflow
anchored to the Task 5.2 contract.

Recorded implementation surfaces:

- `scripts/training/run_phase5_finetune.py`
- `scripts/training/run_phase5_finetune.ps1`
- `scripts/training/inference_smoke.py`
- `docs/model_training_first_pass.md`
- `config/training_first_pass.example.json`

Task 5.3 outputs are written under `dist/training/<run_id>/` and include:

- deterministic `examples.jsonl` and `manifest.json`
- saved `run_config.json` and `run_metadata.json`
- LoRA adapter artifact directory
- inference smoke report (`inference_smoke.json`)

This remains outside the current supported operator/runtime surface until Task
5.4 integrates the trained model path conservatively behind explicit controls.

## Phase 5.4 Conservative Runtime Integration Record

On March 11, 2026, Task 5.4 added a conservative optional runtime path for a
Task 5.3 adapter artifact without widening the default operator baseline.

Recorded implementation surfaces:

- `earCrawler/config/llm_secrets.py`
- `earCrawler/rag/local_adapter_runtime.py`
- `earCrawler/rag/llm_runtime.py`
- `service/api_server/rag_service.py`
- `config/llm_secrets.example.env`

The runtime constraints are:

- the local model path is opt-in only and selected with
  `LLM_PROVIDER=local_adapter`
- local generation is additionally gated by
  `EARCRAWLER_ENABLE_LOCAL_LLM=1`
- runtime config must point at a Task 5.3 adapter directory and matching base
  model via `EARCRAWLER_LOCAL_LLM_ADAPTER_DIR` and
  `EARCRAWLER_LOCAL_LLM_BASE_MODEL`
- the runtime requires the recorded Task 5.3 artifact files
  `run_metadata.json` and `inference_smoke.json` before serving
- the existing evidence/refusal/output-schema safeguards remain unchanged; the
  local model path reuses the same prompt contract, refusal policy, strict JSON
  validation, and grounded-citation checks as remote providers

This does not promote general local checkpoint serving, benchmark execution, or
training workflows into the default runtime surface. It adds one narrowly gated
optional serving path through `/v1/rag/answer` for the production candidate
adapter produced by Task 5.3.
