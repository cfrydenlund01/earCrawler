# Execution Plan 11.5

Source guidance:

- `docs/production_beta_readiness_review_2026-03-25.md`
- `docs/Archive/ExecutionPlanRunPass11.md` as structure/template only
- `docs/kg_quarantine_exit_gate.md`
- `docs/kg_unquarantine_plan.md`
- `docs/model_training_surface_adr.md`
- `docs/model_training_contract.md`
- `docs/model_training_first_pass.md`
- `docs/local_adapter_release_evidence.md`
- `docs/ops/release_process.md`
- `docs/ops/windows_single_host_operator.md`

Prepared: March 25, 2026

## Purpose

This document replaces directionless review loops with one execution path to a
production-ready result for the supported Windows single-host baseline.

The finish line is not "another assessment." The finish line is:

1. release evidence is trustworthy again,
2. the supported host baseline is reproducible on a clean machine,
3. the real corpus -> retrieval -> KG -> API path is current and validated,
4. KG-backed runtime features are either unquarantined with evidence or kept
   explicitly out of scope,
5. the local-adapter path is either evidence-backed with a real QLoRA candidate
   or remains deliberately non-release,
6. a final production decision can be made from current artifacts instead of
   aspiration.

## Model Guidance

Working rule:

- Use `GPT-5.3-Codex` for implementation, tests, scripts, CI, packaging, and
  workflow repair.
- Use `GPT-5.4` for architecture, support-boundary decisions, operator docs,
  and dated decision records.
- Use `GPT-5.4-Mini` only for bounded documentation refreshes, evidence-index
  alignment, or small non-architectural cleanup.
- Use `medium` when the task is bounded and the target state is already clear.
- Use `high` when a task spans multiple modules, changes release/operator
  behavior, or must preserve support boundaries carefully.
- Use `extra high` only once: the final production decision step.

This plan intentionally keeps `extra high` to one final synthesis step.

## Non-Negotiable Strengths To Preserve

- Keep the supported product claim narrow: one Windows host, one API instance,
  one local read-only Fuseki dependency.
- Preserve authored-source versus generated-artifact separation.
- Preserve release evidence discipline and checksum/signature verification.
- Preserve the advisory-only, abstention-first answer posture unless a later
  dated decision explicitly widens it.
- Do not silently promote optional or quarantined capabilities.
- Keep rollback paths and default-off safety controls intact while expanding
  capability evidence.

## Execution Rules

- Do not start a later phase until the current phase gate passes.
- Every prompt step must end with updated artifacts, targeted verification, and
  a brief completion record.
- Every command step must save or confirm evidence under `dist/`, `kg/reports/`,
  or the dated docs named in that phase.
- If a gate fails, execute the contingency in that phase before moving on.

## Phase 0 - Baseline Capture And Workstream Lock

Goal: record the current state once, lock the target, and stop drifting between
review and implementation.

### Step 0.1 - Capture The Current Baseline
Explanation: run the current checks once and record the real starting point for
this plan.

Type: `Code`

```powershell
py -3 -m pytest -q
pwsh scripts/workspace-state.ps1 -Mode verify
pwsh scripts/release-evidence-preflight.ps1 -AllowEmptyDist
pwsh scripts/verify-release.ps1 -RequireCompleteEvidence
pwsh scripts/bootstrap-verify.ps1
```

Expected evidence:

- current pass/fail console output copied into the execution log for this run
- no new interpretation work yet; just a fixed baseline

### Step 0.2 - Create A Single Tracking Record For ExecutionPlan11.5
Explanation: create one dated progress log tied to this plan so work stops
fragmenting across ad hoc notes.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/ExecutionPlan11.5_log.md as the execution log and if not done already seed it with the current Phase 0 baseline results only. Keep it short and operational: date, command run, pass/fail, artifact path if any, and next blocking step. Do not create a new plan or new review. Cross-link only the minimum governing docs. Afterward, ensure this execution log is referenced by name in docs/ExecutionPlan11.5.md where explicitly or implicitly referenced.
```

Phase gate:

- baseline commands have been run once
- one execution log exists and names the current blockers

Contingency if gate fails:

- if the log draft expands into another narrative review, replace it with a
  terse run ledger before continuing

Phase 0 dependency note:

- Phase 1 is the remediation stream for the blockers found in Phase 0.
- Do not advance to Phase 2 or later until the Phase 0 gate passes.

## Phase 1 - Restore Release Trust

Goal: make the live workspace pass its own release-integrity rules again.

This phase is intentionally part of the path to satisfying the Phase 0 gate.
Steps 1.1, 1.2, 1.3, and 1.4 are the remediation work that must close the
baseline blockers before the plan can advance.

### Step 1.1 - Repair `dist/` Integrity And Remove Uncontrolled Release Drift
Explanation: the March 25 review identified stale checksum references and
uncontrolled top-level artifacts as the first hard blocker.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use docs/production_beta_readiness_review_2026-03-25.md and docs/ops/release_process.md as governing context. Repair the live dist/ workspace so release evidence is trustworthy again. Fix the checksum drift between dist/checksums.sha256 and the current retained artifacts, remove or re-home uncontrolled top-level release artifacts that do not belong beside checksums, and preserve the repo's strict publication guards.

Do not weaken verification. Prefer the smallest defensible change set across release scripts, tests, manifests, and retained evidence. End by running the narrowest release-integrity verification needed and summarizing exactly what was changed, what artifacts are authoritative now, and what manual operator assumptions still remain.
```

### Step 1.2 - Rebuild And Verify The Release Evidence Chain
Explanation: once `dist/` is controlled, regenerate and verify the release
evidence expected by the supported release process.

Type: `Code`

```powershell
pwsh scripts/release-evidence-preflight.ps1 -AllowEmptyDist
pwsh scripts/checksums.ps1
pwsh scripts/sign-manifest.ps1 -FilePath dist/checksums.sha256
pwsh scripts/security-baseline.ps1 -Python py -RequirementsLock requirements-win-lock.txt -PipAuditIgnoreFile security/pip_audit_ignore.txt -OutputDir dist/security
pwsh scripts/verify-release.ps1 -RequireCompleteEvidence
```

### Step 1.3 - Align Bootstrap Verification With The Supported Java Floor
Explanation: the supported Fuseki auto-provision flow now expects Java 17+ even
though the bootstrap verifier only caught the current host at Java 8 vs minimum
11. The host and the docs/scripts must agree.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use docs/production_beta_readiness_review_2026-03-25.md, docs/ops/release_process.md, docs/ops/windows_fuseki_operator.md, README.md, and scripts/bootstrap-verify.ps1 as governing context. Tighten the repo's bootstrap/runtime prerequisite story so maintainers and operators can see the difference between the absolute Java minimum and the Java 17+ requirement for the supported Fuseki auto-provision release path. Update the narrowest scripts/docs/tests necessary, without broadening the support claim.

Finish by running the relevant verifier(s) and summarize the final prerequisite contract in one short paragraph.
```

### Step 1.4 - Verify Host Prerequisites On The Active Machine
Explanation: after the repo is aligned, confirm the active machine actually
meets the supported floor.

Type: `Code`

```powershell
java -version
pwsh scripts/bootstrap-verify.ps1
```

Phase gate:

- `scripts/release-evidence-preflight.ps1 -AllowEmptyDist` passes
- `scripts/verify-release.ps1 -RequireCompleteEvidence` passes
- `scripts/bootstrap-verify.ps1` passes on the active host

Contingency if gate fails:

- if `dist/` still drifts, stop and re-run Step 1.1 instead of layering more
  evidence on stale artifacts
- if Java still fails, install or repair JDK 17+ first; do not start clean-host
  or Fuseki proof work on an unsupported machine

## Phase 2 - Re-Prove The Supported Windows Single-Host Baseline

Goal: make the supported deployment story reproducible in the real field shape.

### Step 2.1 - Harden The Clean-Host Install And Smoke Path
Explanation: the release/install path must work from release artifacts, not
just from a checkout.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use docs/production_beta_readiness_review_2026-03-25.md, docs/ops/windows_single_host_operator.md, docs/ops/release_process.md, and the current installed-runtime smoke path as governing context. Close any remaining gap between source-checkout success and the supported clean-host Windows single-host install shape: wheel + hermetic bundle + local read-only Fuseki + API service.

Keep scope tight. Reuse the existing installed-runtime smoke, optional-runtime smoke, health contract, and operator scripts where possible. Do not add multi-instance or container claims. End by running targeted verification and summarizing exactly what is now proven on a clean host.
```

### Step 2.2 - Execute Installed Runtime Smoke In Release Shape
Explanation: prove the supported install path using the actual release-shaped
artifact flow.

Type: `Code`

```powershell
pwsh scripts/installed-runtime-smoke.ps1 `
  -WheelPath dist/earcrawler-*.whl `
  -UseHermeticWheelhouse `
  -HermeticBundleZipPath dist/hermetic-artifacts.zip `
  -ReleaseChecksumsPath dist/checksums.sha256 `
  -UseLiveFuseki `
  -AutoProvisionFuseki `
  -RequireFullBaseline `
  -Host 127.0.0.1 `
  -Port 9001 `
  -ReportPath dist/installed_runtime_smoke.json
```

### Step 2.3 - Execute Supported API Smoke And Observability Probe
Explanation: verify the runtime contract and supported routes on the validated
install shape.

Type: `Code`

```powershell
pwsh scripts/api-start.ps1 -Host 127.0.0.1 -Port 9001
pwsh scripts/api-smoke.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/api_smoke.json
pwsh scripts/health/api-probe.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/observability/health-api.txt -JsonReportPath dist/observability/api_probe.json
pwsh scripts/api-stop.ps1
```

### Step 2.4 - Execute Optional Runtime Smoke Without Local Adapter
Explanation: keep the current baseline honest while proving the quarantine and
rollback controls still behave correctly.

Type: `Code`

```powershell
pwsh scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -SkipLocalAdapter -ReportPath dist/optional_runtime_smoke.json
```

Phase gate:

- `dist/installed_runtime_smoke.json` is passing
- `dist/api_smoke.json` is passing
- `dist/observability/api_probe.json` is passing
- `dist/optional_runtime_smoke.json` is passing

Contingency if gate fails:

- if installed-runtime smoke fails, return to release packaging and operator
  script repair before touching KG or training work
- if only optional-runtime smoke fails, fix the gating/rollback behavior before
  considering any feature promotion

## Phase 3 - Gather And Freeze The Real Corpus

Goal: move from fixture-safe confidence to a current, authoritative corpus and
snapshot chain.

### Step 3.1 - Validate Source Credentials And Live Ingest Readiness
Explanation: confirm the host can gather real upstream data before rebuilding
the corpus.

Type: `Code`

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES='1'
$env:EARCTL_USER='test_operator'
py -m earCrawler.cli jobs run tradegov --dry-run
py -m earCrawler.cli jobs run federalregister --dry-run
```

### Step 3.2 - Build And Validate The Curated Corpus From Real Sources
Explanation: produce fresh corpus artifacts from real inputs, not fixtures.

Type: `Code`

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES='1'
$env:EARCTL_USER='test_operator'
py -m earCrawler.cli corpus build -s ear -s nsf --out data --live
py -m earCrawler.cli corpus validate --dir data
py -m earCrawler.cli corpus snapshot --dir data --out dist/corpus
```

### Step 3.3 - Lock Training-Authoritative Inputs And Provenance
Explanation: make the rebuilt corpus and snapshot the current training truth,
with no leakage from eval, tests, or scratch data.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use docs/model_training_contract.md, docs/data_artifact_inventory.md, docs/offline_snapshot_spec.md, and the outputs from Phase 3 as governing context. Tighten the repository's authoritative training-input path so the current approved offline snapshot, retrieval corpus, and index metadata are the only production training defaults. Prevent accidental drift toward eval, fixture, experimental, or stale corpus inputs. Update the smallest set of docs/config/tests needed and verify the contract.
```

### Step 3.4 - Record The Current Snapshot For Later KG And Training Evidence
Explanation: capture the exact snapshot identity, payload hash, corpus digest,
and doc count that all later phases must use.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `low`

Prompt:
```text
Create or refresh one dated artifact index entry that records the current approved offline snapshot id, snapshot sha256, retrieval corpus path, retrieval corpus digest, index metadata path, and corpus document count produced in Phase 3. Keep it short and machine-oriented. Do not create a new design note.
```

Phase gate:

- live corpus build succeeds
- `py -m earCrawler.cli corpus validate --dir data` passes
- a current snapshot and corpus digest are recorded for later KG/training work

Contingency if gate fails:

- if live ingest blocks on credentials or upstream availability, do not proceed
  with training; fix ingest readiness first
- if the live corpus build is unstable, repair deterministic corpus generation
  before KG or adapter work

## Phase 4 - Rebuild The KG And Satisfy The Technical Exit Criteria

Goal: prove the real corpus -> KG -> validation chain before making any
unquarantine decision.

### Step 4.1 - Emit And Validate The KG From The Current Corpus
Explanation: regenerate KG artifacts from the current corpus and run the
blocking semantic checks that matter for a real promotion decision.

Type: `Code`

```powershell
py -m earCrawler.cli kg emit -s ear -s nsf -i data -o data\kg
py -m earCrawler.cli kg validate --glob "data/kg/*.ttl" --fail-on supported
```

### Step 4.2 - Close Any Remaining KG Integrity, Namespace, Or Provenance Gaps
Explanation: if the current corpus or KG output exposes namespace, identifier,
or lineage regressions, fix them now before touching runtime promotion.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use docs/kg_quarantine_exit_gate.md, docs/kg_unquarantine_plan.md, docs/kg_boundary_and_iri_strategy.md, docs/identifier_policy.md, docs/kg_semantic_blocking_checks.md, and the Phase 4.1 KG validation output as governing context. Close the remaining code, test, or artifact gaps that prevent the current corpus -> KG pipeline from satisfying the technical correctness prerequisites for a future unquarantine decision.

Keep the work concrete: fix integrity/provenance/identifier issues, add targeted tests, and preserve the current narrow support boundary. End by rerunning the exact validation needed to prove the corrected state.
```

### Step 4.3 - Prove Production-Like KG Runtime Mechanics
Explanation: the exit gate requires more than emit/validate; it requires a real
load/serve/query shape.

Type: `Code`

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES='1'
$env:EARCTL_USER='test_operator'
py -m earCrawler.cli kg load --ttl data\kg\ear.ttl --db db
py -m earCrawler.cli kg serve --db db --dataset /ear --no-wait
py -m earCrawler.cli kg query --endpoint http://localhost:3030/ear/sparql --sparql "SELECT * WHERE { ?s ?p ?o } LIMIT 5" --out dist/kg_query_results.json
```

### Step 4.4 - Refresh The Search/KG Quarantine Evidence Package From Current Facts
Explanation: even if KG remains quarantined for one more phase, the evidence
package must stop referring to stale release-integrity facts.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/search_kg_quarantine_decision_package_2026-03-19.md, dist/search_kg_evidence/*, and the completed Phase 1 through Phase 4 evidence as governing context. Refresh the search/KG quarantine record so it cites the current release-integrity story and current runtime evidence instead of stale March 19 assumptions. Keep the capability state unchanged unless the fresh evidence truly justifies reopening promotion work.
```

Phase gate:

- KG emit and validate pass against the current corpus
- a real load/serve/query path has been exercised successfully
- the quarantine evidence package is current, not stale

Contingency if gate fails:

- if KG emit/validate fails, fix the data or emitter first
- if load/serve/query fails, stop and repair the real runtime mechanics before
  any unquarantine decision

## Phase 5 - Decide Whether KG Can Leave Quarantine

Goal: make one evidence-based decision on KG-backed runtime behavior, with a
default of staying quarantined unless the exit gate is fully passed.

### Step 5.1 - Implement The Missing Operator-Owned Search/KG Runtime Proof
Explanation: `/v1/search` and KG expansion cannot leave quarantine without the
operator-owned text-index and success-path proof named by the exit gate.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `high`

Prompt:
```text
Use docs/kg_quarantine_exit_gate.md, docs/kg_unquarantine_plan.md, docs/search_kg_quarantine_decision_package_2026-03-19.md, docs/ops/windows_single_host_operator.md, and the current optional-runtime smoke path as governing context. Implement the smallest complete operator-owned proof package required to reconsider promotion of /v1/search and KG expansion: text-index-enabled Fuseki provisioning if needed, production-like smoke in the actual supported runtime shape, explicit health/failure/rollback docs, and any release-gated test or script changes needed to keep the promotion evidence honest.

Do not auto-promote the capability. The goal is to make a clean pass/fail decision possible from current evidence.
```

### Step 5.2 - Run The Search/KG Production-Like Evidence Commands
Explanation: once the operator-owned path exists, execute the evidence package.

Type: `Code`

```powershell
pwsh scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -SkipLocalAdapter -ReportPath dist/optional_runtime_smoke.json
py -m scripts.eval.build_search_kg_evidence_bundle --optional-runtime-smoke dist/optional_runtime_smoke.json --installed-runtime-smoke dist/installed_runtime_smoke.json --release-validation-evidence dist/release_validation_evidence.json --out-json dist/search_kg_evidence/search_kg_evidence_bundle.json --out-md dist/search_kg_evidence/search_kg_evidence_bundle.md
```

### Step 5.3 - Make The Dated KG Decision
Explanation: after current evidence exists, either explicitly unquarantine the
scoped KG features or explicitly keep them out of the supported production-beta
baseline.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `high`

Prompt:
```text
Use docs/kg_quarantine_exit_gate.md, docs/kg_unquarantine_plan.md, the refreshed search/KG evidence bundle, the current operator docs, and the completed Phase 4/5 runtime evidence as governing context. Produce one dated decision record with exactly one outcome:

1. Graduate the specifically named KG-backed features, or
2. Keep them quarantined.

The record must link each decision to current evidence, name rollback ownership, and update only the minimum boundary docs that must reflect the result. Do not write a broad review. Write the actual decision record.
```

Phase gate:

- either the exit gate is passed and a dated pass record exists, or
- a fresh dated no-go record exists and the supported product scope remains
  explicit

Contingency if gate fails:

- default to `Keep Quarantined`; do not stall the entire program on KG
  promotion if the supported baseline can still ship without it

## Phase 6 - Re-Activate The Real Training Track

Goal: replace placeholder local-adapter evidence with a real, reviewable
training candidate path.

### Step 6.1 - Reopen The Local-Adapter Track Deliberately
Explanation: the repo currently marks the track deprioritized. Reopen it only
if Phase 1 through Phase 5 are stable enough that model work is not building on
an untrustworthy baseline.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `medium`

Prompt:
```text
Use docs/local_adapter_deprioritization_2026-03-25.md, docs/model_training_surface_adr.md, docs/model_training_contract.md, docs/local_adapter_release_evidence.md, and the completed baseline evidence from Phases 1 through 5 as governing context. Produce one short dated reactivation note for the local-adapter track only if the repository baseline is now stable enough for real candidate work. If it is not stable, say so explicitly and name the remaining blocker. Keep the note operational, not aspirational.
```

### Step 6.2 - Prepare A Real Training Run Configuration With Current Snapshot Inputs
Explanation: the training config must stop using placeholder values and must
bind to the current snapshot/corpus digests from Phase 3.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use config/training_first_pass.example.json, config/training_input_contract.example.json, docs/model_training_contract.md, and the current Phase 3 artifact index as governing context. Create the smallest non-placeholder, execution-ready local training config at dist/training/current_training_config.json for a real first-pass candidate using Qwen/Qwen2.5-7B-Instruct and the current approved snapshot/corpus values. Preserve the rule that eval and benchmark datasets remain excluded from training inputs. If a small validator or config guard is needed so placeholder snapshot fields cannot accidentally ship, add it.
```

### Step 6.3 - Generate The Training Package Without Launching Full Training
Explanation: prove the inputs and package are correct before consuming GPU time.

Type: `Code`

```powershell
py scripts/training/run_phase5_finetune.py `
  --config dist/training/current_training_config.json `
  --prepare-only
```

### Step 6.4 - Enforce QLoRA For The Real Candidate Path
Explanation: the repository already supports 4-bit loading via `--use-4bit`,
but the real candidate path must treat that as intentional, not optional drift.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use scripts/training/run_phase5_finetune.py, docs/model_training_first_pass.md, docs/local_adapter_release_evidence.md, and the current training config as governing context. Make the real production-candidate training path explicitly QLoRA-backed for the first 7B candidate, with machine-checkable evidence that the reviewed run used the intended 4-bit path. Keep scope narrow: config validation, metadata capture, docs, and any focused tests needed. Do not redesign the training stack.
```

Phase gate:

- a real non-placeholder run config exists
- prepare-only packaging succeeds
- the intended candidate path has explicit QLoRA evidence rules

Contingency if gate fails:

- if prepare-only packaging fails, do not start GPU training
- if QLoRA evidence is ambiguous, fix metadata/config validation before training

## Phase 7 - Train, Smoke, And Benchmark A Real Candidate

Goal: produce one evidence-backed local-adapter candidate that can actually be
reviewed.

### Step 7.1 - Run The Real QLoRA Fine-Tuning Pass
Explanation: execute the first actual candidate run against the approved base
model and current corpus.

Type: `Code`

```powershell
py scripts/training/run_phase5_finetune.py `
  --config dist/training/current_training_config.json `
  --use-4bit
```

### Step 7.2 - Re-Run Standalone And API Runtime Smokes
Explanation: a candidate is not reviewable unless both the adapter artifact and
the supported `/v1/rag/answer` runtime path work.

Type: `Code`

```powershell
py scripts/training/inference_smoke.py `
  --base-model Qwen/Qwen2.5-7B-Instruct `
  --adapter-dir dist/training/<run_id>/adapter `
  --out dist/training/<run_id>/inference_smoke.rerun.json

pwsh scripts/local_adapter_smoke.ps1 -RunDir dist/training/<run_id>
```

### Step 7.3 - Run The Primary Benchmark Suite With Retrieval-Only Control
Explanation: benchmark the actual candidate through the supported API route,
not through notebook-only or direct model calls.

Type: `Code`

```powershell
py -m scripts.eval.run_local_adapter_benchmark `
  --run-dir dist/training/<run_id> `
  --manifest eval/manifest.json `
  --dataset-id ear_compliance.v2 `
  --dataset-id entity_obligations.v2 `
  --dataset-id unanswerable.v2 `
  --smoke-report kg/reports/local-adapter-smoke.json
```

### Step 7.4 - Validate The Release Evidence Bundle For The Candidate
Explanation: force the result into one of the contract outcomes:
`keep_optional`, `reject_candidate`, or `ready_for_formal_promotion_review`.

Type: `Code`

```powershell
py -m scripts.eval.validate_local_adapter_release_bundle `
  --run-dir dist/training/<run_id> `
  --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json `
  --smoke-report kg/reports/local-adapter-smoke.json
```

### Step 7.5 - Repair Candidate Defects Until One Reviewable Outcome Exists
Explanation: the first real run may fail; that is acceptable. What is not
acceptable is stopping with an unreviewable placeholder again.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use the actual dist/training/<run_id>/ artifacts, benchmark summary, release_evidence_manifest.json, and docs/local_adapter_release_evidence.md as governing context. If the current candidate is not reviewable or is rejected, implement the smallest corrective changes needed to produce one genuinely reviewable next candidate. Focus on concrete defects: retrieval readiness, runtime smoke, strict-output failures, threshold misses, or missing evidence artifacts. Preserve the advisory-only answer posture and keep the runtime opt-in.
```

Phase gate:

- at least one named candidate has a complete machine-checkable evidence bundle
- the evidence outcome is either `reject_candidate` or
  `ready_for_formal_promotion_review`

Contingency if gate fails:

- if repeated runs remain `keep_optional`, stop and repair the workflow until it
  can at least produce reviewable evidence; do not claim progress from partial
  artifacts

## Phase 8 - Decide The Product Role Of Generated Answers

Goal: make the local-adapter and answer-generation posture explicit enough for
production release.

### Step 8.1 - Decide Whether The Local Adapter Stays Optional Or Advances
Explanation: even a strong candidate does not auto-promote the capability.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `high`

Prompt:
```text
Use docs/local_adapter_release_evidence.md, docs/answer_generation_posture.md, the reviewable candidate bundle, the benchmark outputs, and the current runtime/operator docs as governing context. Produce one dated capability decision for local-adapter serving with exactly one outcome:

1. remain Optional, or
2. move to formal promotion review for the scoped optional runtime path.

Do not broaden the product claim beyond advisory-only answer generation. Update only the minimum registry/docs required by the decision.
```

### Step 8.2 - Re-Run Optional Runtime Smoke With The Reviewed Candidate
Explanation: if the local-adapter track is still active after Step 8.1, prove
the optional runtime state in the same release-shaped smoke path.

Type: `Code`

```powershell
pwsh scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -LocalAdapterRunDir dist/training/<run_id> -ReportPath dist/optional_runtime_smoke.json
```

### Step 8.3 - Refresh The Supported Answer-Generation Posture
Explanation: bind the answer claim to the current evidence and the actual
capability decision.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `medium`

Prompt:
```text
Use docs/answer_generation_posture.md, the local-adapter capability decision, the reviewable candidate evidence, and the current API/runtime docs as governing context. Refresh the supported answer-generation posture so it exactly matches the evidence-backed runtime shape, abstention requirements, and human-review boundary now in force. Keep the claim narrow and operational.
```

Phase gate:

- the local-adapter capability state is explicitly decided
- optional runtime smoke reflects the current decision
- answer-generation policy is current and evidence-backed

Contingency if gate fails:

- keep local-adapter serving `Optional` and unpromoted; do not let model work
  block the supported baseline release if the baseline is otherwise ready

## Phase 9 - Assemble The Production Release Candidate

Goal: produce one release candidate whose artifacts, operator path, and current
decision records all agree.

### Step 9.1 - Run The Full Release Process Against Current Artifacts
Explanation: build the release candidate using the current repo, current
operator evidence, and current policy decisions.

Type: `Code`

```powershell
pwsh scripts/release-evidence-preflight.ps1 -AllowEmptyDist
pwsh scripts/build-wheel.ps1
pwsh scripts/package-wheel-smoke.ps1 -WheelPath dist/earcrawler-*.whl
pwsh scripts/build-wheelhouse.ps1 -LockFile requirements-win-lock.txt
pwsh scripts/build-exe.ps1
pwsh scripts/make-installer.ps1
pwsh scripts/checksums.ps1
pwsh scripts/sign-manifest.ps1 -FilePath dist/checksums.sha256
pwsh scripts/verify-release.ps1 -RequireSignedExecutables -RequireCompleteEvidence -ApiSmokeReportPath dist/api_smoke.json -OptionalRuntimeSmokeReportPath dist/optional_runtime_smoke.json -InstalledRuntimeSmokeReportPath dist/installed_runtime_smoke.json -SecuritySummaryPath dist/security/security_scan_summary.json -ObservabilityApiProbePath dist/observability/api_probe.json -EvidenceOutPath dist/release_validation_evidence.json
```

### Step 9.2 - Refresh Operator-Facing Release And Rollback Records
Explanation: make sure the shipping artifact, operator guide, and current
capability state all line up.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/ops/windows_single_host_operator.md, docs/ops/release_process.md, service/docs/capability_registry.json, and the completed Phase 9 release evidence as governing context. Make the minimum documentation and evidence-index updates needed so the operator handoff matches the actual release candidate that is about to be judged. Do not create new roadmap notes or reviews.
```

Phase gate:

- the release verifier passes with complete evidence
- operator docs and capability registry reflect the current release candidate

Contingency if gate fails:

- if the release verifier fails, return to the failing upstream phase instead of
  patching around the verifier

## Phase 10 - Final Production Decision

Goal: make the one repository-wide judgment that justifies ending this plan.

### Step 10.1 - Production-Ready Beta Decision
Explanation: this is the only step that should use `extra high` because it is
the only non-decomposable repository-wide synthesis.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `extra high`

Prompt:
```text
Use docs/ExecutionPlan11.5.md, docs/production_beta_readiness_review_2026-03-25.md, the completed outputs from all prior phases, and the current release/operator evidence as governing context. Produce one final decision document that answers only this question: does earCrawler now qualify as production-ready for its supported Windows single-host baseline?

Evaluate:
1. whether the March 25 blockers were actually closed,
2. whether the original strengths were preserved,
3. whether the release/install/operator story is trustworthy,
4. whether KG-backed runtime behavior is either properly evidenced or properly constrained,
5. whether the answer-generation and local-adapter posture is evidence-backed and operationally safe,
6. whether any residual risks are acceptable for the final label.

End with exactly one of:
- Production-ready beta
- Production-ready beta with named constraints
- Not production-ready beta

Do not write a new execution plan. Write the final decision and name the concrete residual constraints or blockers.
```

Completion condition:

- this final decision is the only remaining review artifact
- if the result is positive, the repo has current evidence to support it
- if the result is negative, the residual blockers must be concrete and few

## Recommended Execution Order

1. Finish Phase 0 and Phase 1 without parallelizing unrelated feature work.
2. Finish Phase 2 before relying on any deployment or runtime claim.
3. Finish Phase 3 before KG or training work.
4. Finish Phase 4 before reopening KG promotion.
5. Execute Phase 5 once current KG evidence exists; default to quarantine if it
   does not pass cleanly.
6. Reopen training only after the baseline and release path are stable.
7. Do not run the final production decision until every intended artifact and
   dated decision record exists.

## Notes On Scope Discipline

- Do not use KG promotion as an excuse to delay the supported baseline release
  if the baseline can ship with KG still quarantined.
- Do not use local-adapter experimentation as a substitute for shipping the
  supported baseline.
- Do not claim QLoRA success from a config flag alone; require run metadata and
  evidence.
- Do not use `extra high` for implementation steps just because they touch
  multiple files.
- If a phase is blocked by missing external prerequisites, stop and clear that
  blocker before consuming more repo context.
