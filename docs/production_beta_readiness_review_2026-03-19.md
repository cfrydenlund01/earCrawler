# Production Beta Readiness Review

Decision date: March 19, 2026

Decision: `Production beta ready with named constraints`

Repository: `earCrawler`

Governing context:

- `docs/ExecutionPlanRunPass10.md`
- `docs/RunPass10.md`
- `docs/capability_graduation_boundaries.md`
- `docs/search_kg_quarantine_decision_package_2026-03-19.md`
- `docs/local_adapter_release_evidence.md`
- `docs/ops/windows_single_host_operator.md`
- `docs/ops/release_process.md`
- `docs/security.md`

## Decision Summary

The supported EarCrawler baseline now qualifies as a production-beta baseline
for the documented Windows single-host deployment shape:

- one Windows host
- one EarCrawler API service instance
- one local read-only Fuseki dependency
- loopback binding by default, or the approved IIS front-door pattern for any
  broader exposure

This is not an unconditional release-publication decision. The repo is now
coherent enough to treat the supported baseline as production beta, but the
current workspace evidence and publication verdict are still bounded by the
actual signing material used on the release machine.

Why the result is not `Production beta ready` without constraints:

- optional local-adapter serving is still not promotion-ready
- `/v1/search` and KG expansion remain intentionally quarantined
- runtime state remains explicitly process-local and therefore single-instance
  only
- this workspace's signed publication proof uses a locally trusted signing
  certificate rather than an organization-managed public-distribution identity

Those remaining limits are acceptable for a production-beta designation because
they are now explicit, documented, tested, and reflected in the runtime
contract instead of being ambiguous.

## Evidence Reviewed

Current validation and evidence used for this review:

- `py -3 -m pytest -q`
  - result: `481 passed, 8 skipped`
  - date run for this review: March 19, 2026
- `dist/optional_runtime_smoke.json`
  - result: `passed`
- `dist/security/security_scan_summary.json`
  - result: `passed`
- `dist/installed_runtime_smoke.json`
  - result: `passed`
  - now proves:
    - `install_mode = hermetic_wheelhouse`
    - `install_source = release_bundle`
- `dist/release_validation_evidence.json`
  - result: refreshed and fully passing
  - now proves:
    - dist artifact checksum verification executed
    - canonical manifest signature verifies
    - release checksums signature verifies
    - installed-runtime smoke passes
    - security baseline passes
    - observability API probe passes
- `scripts/verify-release.ps1 -RequireSignedExecutables -RequireCompleteEvidence`
  - result: passes for the current locally signed workspace
- `dist/earctl-0.2.5-win64.exe`
  - result: present and Authenticode-valid for the current machine trust store
  - signer: `CN=EAR Crawler Local Release Signing`
- `dist/training/step52-real-candidate-gpt2b-20260319/release_evidence_manifest.json`
  - decision: `keep_optional`
  - candidate review status: `not_reviewable`
- `docs/search_kg_quarantine_decision_package_2026-03-19.md`
  - decision: `Keep Quarantined`

## What RunPass10 Strengths Were Preserved

The key strengths identified in `docs/RunPass10.md` remain intact:

- support-boundary discipline is still explicit in code and docs
- deterministic corpus and KG artifact discipline remains in place
- the Windows single-host operator story is still the supported baseline
- optional and quarantined capabilities are still prevented from silently
  becoming default claims
- release and evidence tooling became stricter rather than looser

The supported-versus-optional-versus-quarantined split is now materially more
consistent across:

- `service/docs/capability_registry.json`
- `/health` runtime contract output
- `docs/repository_status_index.md`
- operator documentation
- release smoke and optional-runtime smoke

## RunPass10 Weakness Review

| RunPass10 concern | Current state | Review outcome |
| --- | --- | --- |
| Upstream client failures were too lossy | Explicit upstream status objects now distinguish `no_results`, `missing_credentials`, `upstream_unavailable`, `invalid_response`, and `retry_exhausted`; degraded status is surfaced in callers, manifests, logs, and `/health` live-source reporting. | Resolved for the supported baseline. |
| Startup and optional-runtime hot spots were under-tested | The suite now passes at `481` tests, with added coverage for app startup wiring, runtime-state access, local-adapter runtime, retriever components, upstream clients, and release verification behavior. | Resolved enough for production-beta confidence. |
| Release-grade install path was ambiguous | The operator guide now names the hermetic release bundle as the authoritative release-grade path and separates quick install as a non-release-grade fallback. | Mostly resolved. The process is clear and the release evidence has been refreshed; remaining strict publication blockers are signing-related. |
| CI security evidence lagged behind functional testing | Security baseline outputs now exist and pass, and release verification expects security evidence. | Resolved. |
| API bootstrap was too concentrated | `service/api_server/__init__.py` now delegates lifecycle, contract, request logging, and route/doc wiring into smaller modules. | Resolved as a maintainability improvement. |
| Retriever and corpus builder were too concentrated | Retriever responsibilities are split across backend, ranking, and artifact-store helpers. Corpus builder responsibilities now use supporting artifact, metadata, record, and source modules. | Resolved as an internal maintainability improvement. |
| Runtime state assumptions were implicit | Runtime state is now explicit in `service/api_server/runtime_state.py` and exposed in the runtime contract as process-local. | Resolved for clarity, intentionally still single-instance only. |
| Local-adapter promotion criteria were ambiguous | The repo now has a machine-checkable evidence contract, validator, and candidate-bundle builder. | Resolved as a governance improvement, but not as a capability promotion. |
| Search and KG runtime posture was ambiguous | The repo now carries a dated quarantine decision package and keeps both capabilities gated and default-off. | Resolved as a governance decision; promotion remains blocked. |
| External auth pattern was documentation-light | The repo now ships one Windows-friendly approved front-door pattern plus an IIS reference config. | Resolved for the supported exposure boundary. |
| Backup/restore evidence was ad hoc | Recurring DR evidence automation now exists for API and Fuseki backup plus restore drills. | Resolved for the supported operator baseline. |

## Remaining Constraints And Release Blockers

The following items still materially constrain the production-beta designation.

### 1. Release Publication Now Passes Locally, But Signing Identity Still Matters

The strict repository publication gate now passes for the current workspace.

The earlier evidence gaps were closed during the release-evidence refresh and
the signing/publication pass:

- `dist/checksums.sha256` now exists and is verified
- `dist/checksums.sha256.sig` now exists and verifies
- `dist/observability/api_probe.json` now exists and passes
- `dist/installed_runtime_smoke.json` now proves the expected
  `hermetic_wheelhouse` plus `release_bundle` install shape
- `kg/canonical/manifest.json.sig` now exists and verifies
- `dist/earctl-0.2.5-win64.exe` now exists and passes Authenticode validation

The remaining constraint is about signing provenance rather than missing
artifacts:

- the current pass uses a locally trusted self-signed certificate
- the repository verifier accepts that proof because it checks local signature
  validity, not external trust policy
- external distribution should still use the organization's approved signing
  identity on the actual release machine if broader trust is required

Effect on decision:

- does not block the repo's strict publication gate for this workspace
- still merits an explicit constraint so local signing proof is not confused
  with public-distribution trust policy

### 2. Runtime topology remains intentionally single-host and single-instance

This is acceptable for beta because it is now explicit everywhere that matters,
but it is still a real product boundary:

- rate limits are process-local
- the RAG query cache is process-local
- retriever warm/cache state is process-local
- multi-instance correctness is still unsupported

Effect on decision:

- acceptable named constraint
- not acceptable to widen into scale-out claims without new architecture work

### 3. Local-adapter serving remains optional and not promotion-ready

The local-adapter evidence contract is better, but the current candidate does
not pass it. The reviewed candidate remains:

- `Optional`
- not reviewable for promotion
- not part of the production-beta baseline

Effect on decision:

- not a baseline blocker because the capability remains optional
- still a blocker for any production claim about local-adapter serving

### 4. Search and KG expansion remain quarantined

The quarantine posture is now cleaner and better justified, but promotion has
not happened.

Effect on decision:

- not a baseline blocker because both surfaces remain excluded from the default
  supported contract
- still blocks any production claim for `/v1/search` or KG-backed runtime
  expansion

## Capability Posture After Phase 5 Review

Production-beta baseline includes:

- deterministic corpus and KG build path
- supported CLI and Windows operator path
- default read-only API surface:
  - `/health`
  - `/v1/entities/{entity_id}`
  - `/v1/lineage/{entity_id}`
  - `/v1/sparql`
  - `/v1/rag/query`

Still optional:

- `/v1/rag/answer`
- hybrid dense plus BM25 retrieval
- local-adapter serving

Still quarantined:

- `/v1/search`
- KG expansion during RAG

This separation is now internally consistent enough to trust.

## Final Judgment

Decision: `Production beta ready with named constraints`

Named constraints:

1. The supported product remains exactly the documented Windows single-host,
   single-instance baseline.
2. Direct network exposure of the EarCrawler app remains unsupported; any
   broader exposure must use the approved front-door pattern.
3. The current workspace passes the repo's strict signed-publication gate, but
   the signing identity used here is a locally trusted certificate rather than
   an organization-managed public-distribution identity.
4. Local-adapter serving remains optional and unpromoted.
5. `/v1/search` and KG expansion remain quarantined.

Production-beta is justified because the repo now demonstrates:

- a coherent supported baseline
- strong automated verification
- explicit runtime and operator boundaries
- materially improved release, security, and observability governance
- disciplined containment of immature capabilities

The remaining work is no longer mainly about discovering the product boundary.
It is now about finishing release evidence refresh and, separately, deciding
whether any optional or quarantined capability ever deserves promotion.
