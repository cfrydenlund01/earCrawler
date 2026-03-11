# Runtime Versus Research Boundary

Prepared: March 9, 2026

## Purpose

This document tells contributors which parts of the repository are part of the
supported product/runtime surface and which parts are research, proposal, or
other exploratory material.

Use this before treating a directory, script, or design note as a production
commitment.

## Supported product/runtime surface

The supported runtime surface in this repository is narrow by design:

- operator entrypoints: `earctl` / `py -m earCrawler.cli ...`
- service entrypoint: `service.api_server`
- runtime code those entrypoints import from `earCrawler/`, `api_clients/`, and
  `service/`
- operator packaging, bundle, and Windows service assets under `bundle/`,
  `packaging/`, `service/windows/`, and the documented PowerShell helpers under
  `scripts/`
- operator-facing docs in `README.md`, `RUNBOOK.md`, `docs/api/`, `docs/ops/`,
  and `service/docs/`

A contributor should assume these areas are expected to stay installable,
tested, and aligned with the documented Windows-first operator flow.

## Research and exploratory surface

The repository also contains material that is useful for planning, evaluation,
or proposal work but is not a supported runtime commitment:

- `Research/` notes, logs, quizzes, and proposal support material
- `docs/proposal/` architecture/security/observability proposal narratives
- phase-gated model-training scripts under `scripts/training/` and associated
  docs/config records (`docs/model_training_*.md`, `config/training_*.json`)
- design notes and ADRs for gated, experimental, or future work unless the root
  `README.md` or `RUNBOOK.md` explicitly promotes them into a supported command
  or service path
- ad hoc benchmark summaries and evaluation writeups intended for research logs
  rather than operator runbooks

These areas may inform future work, but they are not by themselves promises
about what operators can run or what release artifacts must support.

## Quarantined or legacy areas

The following are especially easy to misread as supported runtime surfaces, so
they are called out separately:

- `earCrawler.service.sparql_service`
- `earCrawler.service.legacy.kg_service`
- `earCrawler.ingestion.ingest` (legacy placeholder ingestion pipeline; only
  enabled with `EARCRAWLER_ENABLE_LEGACY_INGESTION=1`)
- KG-backed runtime behavior before the gate in `docs/kg_quarantine_exit_gate.md`
  is explicitly passed and recorded
- experimental retrieval modes or evaluation-only switches that the runbook
  still marks as opt-in

For a quick onboarding map to supported entrypoints, see
`docs/start_here_supported_paths.md`.

## Contributor rule of thumb

Treat a surface as supported only when all of the following are true:

- it has a documented `earctl` or `service.api_server` path
- it is covered by tests appropriate to the operator/runtime claim
- packaging/install expectations are defined
- operator docs or runbooks explain how it is used safely

If those conditions are not met, mark the work as research, experimental,
quarantined, or proposal-only instead of implying production support.
