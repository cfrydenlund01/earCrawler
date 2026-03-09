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
