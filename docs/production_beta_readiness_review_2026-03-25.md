# Production Beta Readiness Review

Decision date: March 25, 2026

Decision: `Not production-ready beta`

Repository: `earCrawler`

Review scope:

- current repository working tree as reviewed on March 25, 2026
- current workspace evidence under `dist/`
- current supported Windows single-host baseline documentation and tests

Governing context:

- `docs/Archive/ExecutionPlanRunPass11.md`
- `docs/Archive/RunPass11.md`
- `docs/answer_generation_posture.md`
- `docs/local_adapter_deprioritization_2026-03-25.md`
- `docs/maintainer_start_here.md`
- `docs/repository_status_index.md`
- `docs/ops/release_process.md`
- `docs/ops/windows_single_host_operator.md`
- `docs/ops/external_auth_front_door.md`

## Decision Summary

The repository remains close to a defensible constrained production-beta shape
for the documented Windows single-host baseline, but the current workspace does
not qualify today.

The main blocker is not feature completeness. It is release trust in the live
workspace. The repo now has the right release guards, operator docs, runtime
boundaries, and test depth, but the reviewed `dist/` state fails those guards:

- `scripts/release-evidence-preflight.ps1 -AllowEmptyDist` fails because
  uncontrolled top-level release artifacts are present beside
  `dist/checksums.sha256`
- `scripts/verify-release.ps1 -RequireCompleteEvidence` fails because
  `dist/checksums.sha256` still references
  `earcrawler-kg-dev-20260319-snapshot.zip`, while the current workspace holds
  `earcrawler-kg-dev-20260325-snapshot.zip`

That means the current workspace cannot presently support the claim that the
release bundle, retained evidence, and publication gate are trustworthy enough
for a production-beta label.

There is a second practical blocker for reproducibility on this reviewed host:
`scripts/bootstrap-verify.ps1` fails because the host only has Java 8, below
the repository's minimum Java requirement, while the release/install path now
expects Java 17+ for the supported Fuseki auto-provision flow.

## Evidence Reviewed

Current verification run for this review:

- `py -3 -m pytest -q`
  - result: `520 passed, 7 skipped`
  - date run for this review: March 25, 2026
- `pwsh scripts/workspace-state.ps1 -Mode verify`
  - result: passed
  - current ghost-residue paths are absent
- `pwsh scripts/release-evidence-preflight.ps1 -AllowEmptyDist`
  - result: failed
  - failure: uncontrolled top-level artifacts next to checksums:
    - `iis-front-door-smoke-test.json`
    - `iis-front-door-smoke-test.txt`
    - `installed_runtime_smoke.b1.json`
- `pwsh scripts/verify-release.ps1 -RequireCompleteEvidence`
  - result: failed
  - failure: missing dist artifact listed in checksums:
    `earcrawler-kg-dev-20260319-snapshot.zip`
- `pwsh scripts/bootstrap-verify.ps1`
  - result: failed
  - failure: Java major version `8` is below required minimum `11`

Existing retained evidence still present in the workspace:

- `dist/release_validation_evidence.json`
  - dated March 19, 2026
  - status inside file: passing, including checksum signature, installed-runtime
    smoke, security baseline, and observability probe
- `dist/installed_runtime_smoke.json`
  - status: `passed`
  - proves `install_mode = hermetic_wheelhouse`
  - proves `install_source = release_bundle`
- `dist/optional_runtime_smoke.json`
  - status: `passed`
  - proves search default-off -> opt-in -> rollback and KG failure-policy checks
- `dist/observability/api_probe.json`
  - status: `passed`

Capability evidence reviewed:

- `docs/answer_generation_posture.md`
  - generated answers remain advisory-only and abstention-first
- `dist/training/step52-real-candidate-gpt2b-20260319/release_evidence_manifest.json`
  - decision: `keep_optional`
  - candidate review status: `not_reviewable`
- `dist/benchmarks/step52-real-candidate-gpt2b-20260319/benchmark_summary.json`
  - local-adapter answer metrics remain `0.0`
  - strict-output failure rate remains `1.0`
- `docs/search_kg_quarantine_decision_package_2026-03-19.md`
  - decision remains `Keep Quarantined`

## Evaluation Against The E.1 Criteria

### 1. RunPass11 strengths were mostly preserved

The key strengths identified in `docs/Archive/RunPass11.md` remain visible:

- support-boundary discipline is stronger, not weaker
- authored source, generated outputs, optional features, and quarantined
  capabilities are now documented more explicitly
- the supported topology remains deliberately narrow: one Windows host, one API
  service instance, one local read-only Fuseki dependency
- generated-answer posture is more constrained and defensible than before
- test breadth improved from the prior review, with the current suite at
  `520 passed, 7 skipped`

### 2. Weaknesses and missing components were improved unevenly

Resolved or materially constrained:

- workspace/source classification
  - `scripts/workspace-state.ps1 -Mode verify` passes
  - maintainer and repository-status docs now make the source/generated split
    explicit
- maintainer handoff and system-map gap
  - `docs/maintainer_start_here.md` and
    `docs/single_host_runtime_state_boundary.md` close the earlier onboarding
    gap
- single-host runtime-state ambiguity
  - runtime state is now explicit in `service/api_server/runtime_state.py` and
    `/health`
- answer-generation boundary
  - `docs/answer_generation_posture.md` clearly narrows support to grounded
    advisory drafting plus abstention
- local-adapter ambiguity
  - the track is now explicitly deprioritized rather than lingering as implied
    near-term release work

Not fully resolved:

- release-workspace integrity
  - the guard exists, but the current workspace fails it
- release verification hermeticity in the reviewed workspace
  - the verifier exists, but the current `dist/` contents are out of sync with
    the active checksums file
- bootstrap reproducibility on the reviewed host
  - the verifier exists, but the host does not meet the Java prerequisite

Partly stale or inconsistent:

- `docs/search_kg_quarantine_decision_package_2026-03-19.md` and
  `dist/search_kg_evidence/search_kg_evidence_bundle.json` still describe the
  older "checksums file not found" release gap, while
  `dist/release_validation_evidence.json` shows that checksums were later
  restored on March 19, 2026

### 3. Authored source, generated evidence, optional capability, and quarantined capability are clearly separated

This criterion is now largely satisfied.

Strong evidence:

- `docs/repository_status_index.md`
- `docs/data_artifact_inventory.md`
- `docs/maintainer_start_here.md`
- `service/docs/capability_registry.json`
- `/health` runtime contract as captured in `dist/installed_runtime_smoke.json`

Current capability posture is coherent:

- `Supported`: CLI, supported API routes, Windows single-host operator path
- `Optional`: `/v1/rag/answer`, hybrid retrieval, local-adapter serving
- `Quarantined`: `/v1/search`, KG expansion
- `Generated`: `dist/`, `build/`, `run/`, `runs/`, `.venv*`, `.pytest_*`

This is no longer a major blocker.

### 4. Release, deployment, and operator story is improved but not yet trustworthy enough in the current workspace

The repository now contains a credible release and operator design:

- staged GitHub release workflow with build/validate/promote phases
- strict release verifier and preflight guard
- installed-runtime smoke for the actual wheelhouse/release-bundle install shape
- dedicated Windows single-host and Fuseki operator scripts
- explicit IIS front-door reference pattern and smoke test
- recurring backup/restore drill automation

However, the current workspace fails the same release gates that are supposed to
justify trust:

1. `release-evidence-preflight` fails because uncontrolled top-level artifacts
   sit next to the checksum file.
2. `verify-release` fails because the checksum manifest still points at the old
   March 19 snapshot zip.
3. The current host fails bootstrap verification because Java is below the
   documented minimum.

Because this step is an actual repository-and-workspace judgment, these are
current blockers, not merely historical notes.

### 5. The supported answer-generation posture is evidence-backed and operationally safer

This area improved enough to be defensible for a narrow beta claim:

- supported baseline is retrieval-first, not autonomous answering
- `/v1/rag/answer` remains optional, operator-controlled, and abstention-first
- higher-risk use explicitly requires human review
- local-adapter serving remains unpromoted and evidence-failing

This is now properly constrained. It is not the blocker that keeps the repo
from the beta label today.

### 6. Remaining risks are not acceptable for a production-ready beta label today

Acceptable named constraints that are now explicit:

- single-host and single-instance only
- reverse-proxy front door required for broader-than-loopback exposure
- local-adapter serving remains optional and deprioritized
- `/v1/search` and KG expansion remain quarantined

Unacceptable current blockers:

- release evidence in the live workspace is not clean enough to pass its own
  publication guards
- checksum and artifact state in `dist/` is internally inconsistent
- the reviewed host cannot currently satisfy the documented bootstrap/runtime
  prerequisite floor for Java-backed flows

## Residual Blockers

1. `dist/` release state is not publication-clean.
   - `dist/checksums.sha256` still lists
     `earcrawler-kg-dev-20260319-snapshot.zip`
   - `dist/` currently contains
     `earcrawler-kg-dev-20260325-snapshot.zip`
   - extra top-level smoke artifacts are present outside the controlled checksum
     set

2. Release trust is therefore presently split between stale retained evidence
   and a failing live verifier.
   - March 19 evidence says the release path passed
   - March 25 workspace checks say the current release root is no longer in a
     trustworthy state

3. Bootstrap proof is not reproducible on this reviewed host.
   - `scripts/bootstrap-verify.ps1` fails on Java 8
   - the supported release/install path now assumes a newer Java runtime,
     especially for Fuseki auto-provision and clean-host validation

4. Search/KG quarantine records are still partially stale.
   - quarantine remains the correct decision
   - but one dated evidence package still cites an older release-integrity gap
     rather than the current one

## Final Judgment

Decision: `Not production-ready beta`

Why:

- the repo's supported baseline is now narrow, explicit, and technically much
  stronger than the March 19 pre-hardening state
- the current workspace still fails its own release-integrity gates
- production-beta for this project requires a trustworthy release and operator
  story, not only good code structure and passing tests

What would most directly change this verdict:

1. restore `dist/` to a controlled release state so both
   `scripts/release-evidence-preflight.ps1 -AllowEmptyDist` and
   `scripts/verify-release.ps1 -RequireCompleteEvidence` pass again
2. rerun or refresh the retained release evidence against that controlled state
3. rerun bootstrap verification on a host that meets the documented Java floor
4. refresh the stale search/KG decision package inputs so the quarantine record
   matches the current release-integrity story

If those items are closed without widening unsupported claims, the repository
appears close to returning to a defensible
`Production-ready beta with named constraints` judgment for its supported
Windows single-host baseline.
