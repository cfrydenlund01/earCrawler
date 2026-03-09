# KG Quarantine Exit Gate

Status: normative for any change that claims KG-backed runtime behavior is part of the supported production CLI path.

As of March 6, 2026, this gate is not passed. KG-related runtime behavior remains quarantined.

## Purpose

This document defines the go/no-go criteria for moving KG-backed runtime features from quarantine into the supported operator path.

It complements:

- `RUNBOOK.md`
- `docs/kg_boundary_and_iri_strategy.md`
- `docs/identifier_policy.md`
- `docs/done_done_checklist.md`

This document does not unquarantine any feature by itself.

## Current quarantine boundary

Today, the supported runtime surface is:

- `earctl` / `py -m earCrawler.cli ...`
- `service.api_server`

The following are not sufficient to claim that KG is production-ready:

- Existing `kg-*` subcommands by themselves
- Optional environment flags for KG expansion
- Stubbed Fuseki tests
- Source-checkout-only scripts or repo-relative resource loading
- Legacy service modules under `earCrawler.service.*`

## What "KG is part of the production CLI" means

KG is part of the production CLI only when a clean installed artifact, outside a source checkout, supports a documented operator workflow that can:

1. build or obtain the approved KG inputs,
2. validate and export the KG deterministically,
3. load and serve the KG through the supported CLI/service path,
4. exercise every claimed KG-backed runtime feature with release-gated tests, and
5. be operated, monitored, and rolled back from the runbook without relying on undocumented scripts or developer knowledge.

If any one of those conditions is missing, KG remains quarantined.

## Exit criteria

All of the following must be true before unquarantining KG-backed runtime features.

### 1. Runtime boundary is explicit and singular

Required:

- The only supported KG runtime entrypoints are documented operator commands under `earctl` / `py -m earCrawler.cli ...` plus `service.api_server`.
- Legacy services remain quarantined and are not described as production deployment options.
- Any KG-backed API behavior is reachable through the supported service path, not through a separate ad hoc server.

Required evidence:

- `RUNBOOK.md` documents the supported commands and excludes legacy service paths.
- A release note or decision record names the exact supported KG entrypoints.

### 2. KG correctness prerequisites are already met

Required:

- Canonical namespaces and graph identity follow `docs/kg_boundary_and_iri_strategy.md`.
- Citation and section identifiers follow `docs/identifier_policy.md`.
- Integrity validation is a hard gate before export/load.
- Provenance is preserved across duplicate text or equivalent source records; KG-backed answers must not collapse lineage incorrectly.
- Snapshot identity and downstream artifacts record the aligned KG digest.

Required evidence:

- Passing integrity checks from the supported CLI path.
- Passing namespace/identifier/provenance regression tests.
- A documented artifact showing the snapshot digest used for the shipped KG-backed workflow.

### 3. Clean-room packaging and install work

Required:

- The supported KG workflow runs from an installed wheel, signed executable, or installer without a source checkout.
- Required KG resources are packaged or bootstrap deterministically with pinned versions and checksum verification.
- No supported command depends on repo-relative templates, assembler files, or PowerShell-only layout assumptions.

Required evidence:

- A clean-room smoke test that installs the release artifact and exercises the minimum KG workflow end to end.
- Release validation logs showing the packaged artifact contains or provisions the required KG resources.

### 4. End-to-end tests cover the real claimed runtime

Required:

- Offline deterministic tests continue to cover KG emit/load/query behavior.
- At least one production-like smoke test runs against a real Fuseki dataset, not only stubs.
- Every feature claimed as "supported" has a matching end-to-end test in the same runtime shape operators will use.
- CI or release validation blocks shipping when those tests fail.

Required evidence:

- Passing CI/release jobs for deterministic KG validation.
- Passing production-like smoke output for the supported KG-backed path.
- Stored test artifacts or logs attached to the release decision.

### 5. Operator readiness exists in the runbook

Required:

- `RUNBOOK.md` documents install, configuration, start, health checks, shutdown, rollback, and troubleshooting for the supported KG path.
- Monitoring covers both the API surface and its KG dependency.
- Secret/config handling is explicit, including Fuseki endpoint configuration when required.
- RBAC and audit logging cover the supported KG commands and API surface.

Required evidence:

- Runbook sections for the supported KG workflow.
- Operator-facing health and rollback commands exercised during validation.
- Audit/RBAC tests covering the supported commands.

### 6. Failure behavior is defined and conservative

Required:

- The repo documents what happens when Fuseki, graph validation, or KG expansion is unavailable.
- The supported path either fails closed or degrades in an explicitly documented way; it must not silently route through an unsupported fallback.
- Timeouts, health checks, and retry behavior are bounded and test-covered.

Required evidence:

- Tests covering the declared failure policy.
- Runbook language that matches the implemented failure mode.

### 7. The unquarantine decision is recorded

Required:

- A short decision record, ADR, or release note states that the gate passed.
- The record links the evidence for criteria 1 through 6.
- The record names the exact KG-backed features now considered supported.

Required evidence:

- Merged document or release entry with date, approver, artifact links, and scope.

## What remains out of scope until this gate passes

The following remain out of scope for the supported production path until the gate is explicitly passed:

- Jena text-indexed entity search as a supported production feature
- Default-on or production-committed KG expansion in RAG
- Hybrid retrieval work that depends on a supported KG runtime
- Temporal/effective-date reasoning that relies on KG-backed runtime behavior
- Any documentation that portrays Fuseki-backed features as generally production-ready without the gate evidence above

## Pass/fail rule

This gate is binary.

- Pass: every exit criterion above has current evidence and the decision is recorded.
- Fail: any criterion is missing, stale, or only satisfied in a source checkout or stubbed test environment.

Until the gate passes, KG-backed runtime work must be treated as quarantined, optional, or experimental rather than part of the supported production CLI path.
