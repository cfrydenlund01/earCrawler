# earCrawler Execution Plan Going Forward
_Source basis:_ This plan is derived from the uploaded **Run Pass 6** analysis as the primary project source. It translates the report’s findings into an ordered execution plan for work performed in **VS Code on Windows using the Codex plugin**. The only outside-source addition is the requested 7B model recommendation for a future training phase.

## Planning assumptions from the analysis
- Supported production surface is intentionally narrow: **`earctl` + `service/api_server`**.
- The biggest current risks are:
  1. CI validates a **sample TTL generator** instead of the real corpus→KG path.
  2. Documentation is inconsistent on whether **KG-backed search** is truly supported.
  3. Complexity is concentrated in **CLI** and **RAG** hotspots.
- Research benchmarks should wait until there is a **production model**.
- If KG is to be unquarantined, pre-steps must come first: **real corpus discipline, real corpus→KG gate, capability clarity, and ops clarity**.

---

## Phase 0: Operating rules for execution
1. **Use GPT-5.4 for architecture, sequencing, contract decisions, and risk-sensitive refactors.**
2. **Use GPT-5.3-Codex for implementation-heavy edits, tests, CI YAML, and smaller scoped code moves.**
3. **Use Extra High only when the step requires cross-cutting architectural judgment across many files.**
4. **Split Extra High work into smaller bounded tasks** so the model stays grounded and does not smear context across unrelated surfaces.
5. **Do not start benchmark-heavy research evaluation yet.** The analysis supports evaluation rigor, but your note says benchmarks should wait for a production model.

---

## Phase 1: Stabilize the supported path first

### Task 1.1 — Freeze the supported product boundary in docs
**Goal:** Make the repo say one thing, everywhere, about what is supported, optional, quarantined, and proposal-only.  
**Why now:** The analysis identifies capability drift, especially around KG-backed search and `/v1/search`, as a P0 ambiguity that undermines operator trust. fileciteturn1file0

**Deliverables**
- One canonical capability matrix in `README.md`
- Matching language in `RUNBOOK.md`
- Matching language in API docs
- Explicit tags for:
  - Supported
  - Optional
  - Quarantined
  - Proposal-only

**Recommended model:** GPT-5.4  
**Reasoning level:** High  
**Why not Extra High:** This is a bounded product-definition task, not a full architectural redesign.

**Execution notes**
- Treat the analysis as the source of truth.
- Force a single table to drive all downstream docs.
- Explicitly resolve the status of KG-backed search and `/v1/search`.

**Exit criteria**
- No contradictory statements remain between README, runbook, API docs, and quarantine docs.
- A new contributor can identify the supported runtime boundary in under 2 minutes.

---

### Task 1.2 — Rename or relocate the sample TTL pipeline
**Goal:** Stop the sample TTL generator from being mistaken for the real corpus→KG validation path.  
**Why now:** The analysis marks this as the top technical risk because green CI can hide regression in the real supported path.

**Deliverables**
- `build_ttl.py` is either:
  - moved to `tests/fixtures` or equivalent, or
  - renamed so it is unmistakably synthetic/sample-only
- README and CI references updated accordingly

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** Medium  
**Why this level:** This is a focused rename/relocation plus doc touch-up.

**Exit criteria**
- No production-facing document or workflow implies the sample TTL path is the real gate.

---

### Task 1.3 — Replace the fake gate with the real supported corpus→KG gate
**Goal:** Make CI validate the actual supported evidence path.  
**Why now:** This is the strongest correction to the strongest current weakness. The analysis explicitly recommends a canonical end-to-end production gate: corpus build → KG emit → SHACL → API smoke → no-network RAG smoke. fileciteturn1file0

**Deliverables**
- CI workflow changed to validate:
  1. corpus build
  2. KG emission
  3. SHACL validation
  4. API smoke
  5. no-network RAG smoke
- README updated so the documented gate matches reality

**Recommended model:** GPT-5.4  
**Reasoning level:** High  
**Why not Extra High:** The target path is already identified in the analysis; the task is integration, not open-ended design.

**Execution notes**
- Keep the gate aligned with the **supported** path only.
- Do not expand surface area while fixing the gate.

**Exit criteria**
- A green pipeline proves the real supported path, not a synthetic placeholder.
- CI failure clearly indicates which stage failed.

---

## Phase 2: Prepare the ground before any KG unquarantine decision

### Task 2.1 — Build a KG unquarantine checklist from the analysis
**Goal:** Convert the analysis into a concrete pre/post gate document for KG graduation.  
**Why now:** Your note specifically asks for pre and post steps if it is time to unquarantine KG. The analysis says the repo currently lacks a single capability matrix and a canonical production gate, so those must come first. 

**Deliverables**
- `docs/kg_unquarantine_plan.md` or equivalent with:
  - Preconditions
  - Evidence required
  - Post-graduation obligations
  - Rollback conditions

**Required preconditions**
1. Supported capability matrix is unified.
2. Real corpus→KG CI gate exists.
3. SHACL validation is part of the supported path.
4. API smoke and no-network RAG smoke are stable.
5. Operator docs clearly distinguish supported vs optional KG behavior.

**Recommended model:** GPT-5.4  
**Reasoning level:** High

**Exit criteria**
- Completed KG checklist to include pre and post conditions.

---

### Task 2.2 — Decide whether KG-backed search graduates now or stays quarantined
**Goal:** Make one explicit product decision.  
**Why now:** The analysis treats capability drift here as a P0 problem. You should not continue coding against an unresolved support boundary. 

**Decision options**
- **Option A: Keep KG-backed search quarantined**
  - Faster path to a clean beta/near-production single-host handoff
  - Less operational ambiguity
- **Option B: Graduate KG-backed search now**
  - Only if the new gate and operator story are already solid

**Recommended model:** GPT-5.4  
**Reasoning level:** High  
**Why not Extra High:** The analysis narrows the decision space substantially.

**My recommendation from the analysis alone**
- **Keep KG-backed search quarantined until after Tasks 1.1 through 2.1 are complete and stable.**
- Then graduate it only if the supported gate proves the real path cleanly.

**Exit criteria**
- The status of KG-backed search is explicit in code comments, docs, and operational docs.

---

### Task 2.3 — If graduating KG, implement the pre-graduation work
**Goal:** Ensure there is an actual corpus-to-graph story before unquarantine.  
**Why now:** This is the “pre” half of your requested KG sequence.

**Deliverables**
- Real corpus pipeline is the source for KG artifacts
- KG validation is proven in CI
- API docs and capability docs describe the graduated feature correctly
- Search route behavior is documented and tested as supported, not aspirational

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** High  
**Why this level:** Implementation touches multiple files but is still bounded by the decision already made.

**Exit criteria**
- KG-backed behavior is no longer supported only in prose. It is enforced by gates and tests.

---

### Task 2.4 — If graduating KG, implement the post-graduation obligations
**Goal:** Make support sustainable after unquarantine.  
**Why now:** This is the “post” half of your requested KG sequence.

**Deliverables**
- Updated operator docs
- Explicit failure/rollback steps
- Support statement for single-host vs multi-instance behavior
- Regression tests specific to KG-backed search behavior

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** Medium

**Exit criteria**
- A new operator can install, run, validate, and recover KG-backed search without reading proposal docs.

---

## Phase 3: Reduce change risk in the hotspots before adding features

### Task 3.1 — Break CLI monolith into domain registrars
**Goal:** Reduce risk in `earCrawler/cli/__main__.py` by splitting command registration into domain modules.  
**Why now:** The analysis flags CLI concentration as a medium-risk hotspot that increases onboarding cost and regression probability. 

**Deliverables**
- Separate command registrars for:
  - corpus
  - KG
  - RAG
  - eval
  - API or service operations
- Thin top-level CLI entrypoint

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** High  
**Why not Extra High:** This is a classic refactor with clear target decomposition.

**Exit criteria**
- Main CLI file becomes orchestration glue, not the place where domain logic accumulates.

---

### Task 3.2 — Split RAG pipeline planning from execution
**Goal:** Reduce the blast radius in `earCrawler/rag/pipeline.py`.  
**Why now:** The analysis explicitly identifies `rag/pipeline.py`, `rag/retriever.py`, and the API RAG route as behavior-dense modules that should be split before feature growth. fileciteturn1file0

**Recommended model:** GPT-5.4  
**Reasoning level:** Extra High  
**Why Extra High:** This is the most architecture-sensitive refactor in the plan.

Because Extra High should be split, do this as four controlled substeps:

#### Task 3.2a — Extract retrieval orchestration boundaries
- Separate retrieval coordination from response assembly
- Define clean module interfaces

**Model:** GPT-5.4  
**Reasoning:** High

#### Task 3.2b — Extract temporal adjudication and refusal policy
- Move temporal/evidence refusal policy into a dedicated policy layer

**Model:** GPT-5.4  
**Reasoning:** High

#### Task 3.2c — Extract provider invocation and schema validation
- Isolate remote provider interaction and output validation

**Model:** GPT-5.3-Codex  
**Reasoning:** High

#### Task 3.2d — Slim the API RAG route into request/response orchestration only
- API route should delegate instead of containing behavior density

**Model:** GPT-5.3-Codex  
**Reasoning:** Medium

**Exit criteria**
- Each RAG concern has a clear owner module.
- Tests can target retrieval, policy, provider, and route separately.

---

### Task 3.3 — Quarantine or archive visibly misleading experimental surfaces
**Goal:** Stop placeholder or dead-end code from competing with the supported path.  
**Why now:** The analysis names placeholder ingestion and legacy/quarantined services as ongoing sources of contributor confusion. 

**Deliverables**
- Clear `experimental` or `quarantined` banners
- Archive or relocate obvious dead-end modules
- “Start here” developer map pointing to the supported entrypoints

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** Medium

**Exit criteria**
- A new developer is naturally guided toward corpus/KG emit, supported API, and current docs.

**Implementation status (March 10, 2026)**
- Completed.
- Legacy placeholder ingestion was relocated behind a quarantined surface:
  `earCrawler.experimental.legacy_ingest` with gated compatibility import at
  `earCrawler.ingestion.ingest` (`EARCRAWLER_ENABLE_LEGACY_INGESTION=1`).
- Added a developer onboarding map at `docs/start_here_supported_paths.md`.
- Updated `README.md`, `RUNBOOK.md`, and
  `docs/runtime_research_boundary.md` to mark and route away from misleading
  legacy surfaces.

---

## Phase 4: Production hardening for the Windows-first single-host target

### Task 4.1 — Publish coverage and enforce a minimum threshold
**Goal:** Turn strong test breadth into a visible, enforceable signal.  
**Why now:** The analysis notes that coverage reporting exists in configuration but is not enforced in CI. 

**Deliverables**
- Coverage XML publication
- Minimum threshold gate
- CI docs updated to describe the threshold

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** Medium

**Exit criteria**
- Coverage erosion becomes visible and blockable.

---

### Task 4.2 — Define latency and failure budgets for the supported API
**Goal:** Add practical release gates around `/v1/search` and `/v1/rag/query`.  
**Why now:** The analysis says performance budgets are missing as release criteria. 

**Deliverables**
- Budget document
- Smoke/perf checks in CI or release workflow
- Thresholds for:
  - request latency
  - failure rates
  - timeout behavior

**Recommended model:** GPT-5.4  
**Reasoning level:** High  
**Why this level:** Threshold choice is architectural and operator-facing, not just code editing.

**Exit criteria**
- You can state what “fast enough” and “stable enough” mean for the supported surface.

---

### Task 4.3 — Write one authoritative deployment, upgrade, backup, restore, and rollback story
**Goal:** Produce a real operator handoff path for the Windows-first supported target.  
**Why now:** The analysis says deployment automation is incomplete and scattered across scripts/runbooks. 

**Deliverables**
- One operator document covering:
  - fresh install
  - upgrade
  - backup
  - restore
  - rollback
  - secret rotation
- Remove or de-emphasize conflicting operator instructions elsewhere

**Recommended model:** GPT-5.4  
**Reasoning level:** High

**Exit criteria**
- A handoff operator can perform the full lifecycle from one source of truth.

---

### Task 4.4 — Lock in single-host semantics unless scaling is explicitly in scope
**Goal:** Prevent accidental overclaiming of runtime behavior.  
**Why now:** The analysis states that rate limits, concurrency controls, and caches are single-process constructs; scaling would change behavior immediately. fileciteturn1file0

**Deliverables**
- Explicit statement of single-host support in operator docs and README
- Deferred note for future multi-instance design, rather than pretending it already exists

**Recommended model:** GPT-5.4  
**Reasoning level:** Medium  
**Why not High:** This is mostly a support-contract clarification.

**Exit criteria**
- No document implies multi-instance correctness unless it is actually implemented.

---

## Phase 5: Model training only after the production path is clean

### Gate before this phase
Do **not** start training until all of the following are true:
1. Supported runtime boundary is stable.
2. Real corpus→KG gate is in CI.
3. RAG hotspots are refactored enough to support controlled integration.
4. Deployment/recovery story exists.
5. KG status is explicit, whether still quarantined or graduated.

This ordering follows the analysis emphasis on architectural ambiguity over obvious implementation failure. fileciteturn1file0

---

### Task 5.1 — Select the production 7B model
**Recommendation:** **Qwen2.5-7B-Instruct**  
**Why this is a good fit:** It is an openly available 7B instruction model from the Qwen family, with official model and repository pages available. citeturn0search0turn0search1

**Official model page**
- Hugging Face: `Qwen/Qwen2.5-7B-Instruct` citeturn0search0

**Official repository**
- GitHub: `QwenLM/Qwen` citeturn0search1

**Recommended model:** GPT-5.4  
**Reasoning level:** Medium  
**Why this level:** Selection is bounded and based on a straightforward fit to your 7B requirement.

**Exit criteria**
- One production-intended base model is chosen and written into docs/config.

---

### Task 5.2 — Prepare training inputs and training contract
**Goal:** Create a clean training package from the supported evidence path.  
**Why now:** Training should rest on the real corpus and supported retrieval/evidence assumptions, not a moving target.

**Deliverables**
- Defined training dataset sources
- Format contract for instruction tuning examples
- Separation of:
  - production training data
  - eval data
  - future benchmark data

**Recommended model:** GPT-5.4  
**Reasoning level:** High

**Exit criteria**
- You can regenerate the training inputs deterministically.

---

### Task 5.3 — Run first production-oriented 7B fine-tuning pass
**Goal:** Train the first production candidate model.  
**Why now:** Only after the production path is stable should the model become another moving part.

**Deliverables**
- Repeatable training command(s)
- Artifact/version naming
- Saved config and run metadata
- Basic inference smoke test

**Recommended model:** GPT-5.3-Codex  
**Reasoning level:** High  
**Why this level:** This is implementation-heavy and procedural once the training contract exists.

**Exit criteria**
- A named trained model artifact exists and can be loaded into the supported runtime path.

---

### Task 5.4 — Integrate the production candidate model conservatively
**Goal:** Introduce the production model without breaking the evidence-grounded posture.  
**Why now:** The analysis praises the current conservative AI layer; keep that discipline. fileciteturn1file0

**Deliverables**
- Feature-flagged or configuration-gated model integration
- Existing evidence/refusal/schema safeguards remain intact
- Smoke tests updated

**Recommended model:** GPT-5.4  
**Reasoning level:** High

**Exit criteria**
- The trained model can serve through the supported path without relaxing evidence controls.

---

## Phase 6: Only then do benchmarks and broader research evaluation

### Task 6.1 — Build the benchmark plan after a production model exists
**Goal:** Delay benchmark work until it measures the actual production candidate, not a placeholder.  
**Why now:** This follows your explicit note and also fits the analysis emphasis on rigorous groundedness evaluation as a later strength, not the current blocker. fileciteturn1file0

**Recommended model:** GPT-5.4  
**Reasoning level:** Medium

**Exit criteria**
- Benchmarks are defined against the production candidate and supported path.

---

## Recommended execution order summary
1. Freeze supported capability matrix.
2. Rename/relocate sample TTL path.
3. Replace fake CI gate with real corpus→KG gate.
4. Create KG unquarantine checklist.
5. Decide KG status.
6. If graduating KG, do pre- and post-graduation work.
7. Split CLI monolith.
8. Split RAG pipeline in bounded substeps.
9. Quarantine/archive misleading experimental surfaces.
10. Add coverage gate.
11. Add latency/failure budgets.
12. Write single authoritative deployment/recovery flow.
13. Lock single-host semantics.
14. Select 7B production model.
15. Prepare deterministic training contract.
16. Train first production-oriented model.
17. Integrate model conservatively.
18. Only then start benchmark work.

---

## Suggested model/reasoning matrix
| Step | Task | Model | Reasoning |
|---|---|---|---|
| 1.1 | Capability matrix unification | GPT-5.4 | High |
| 1.2 | Rename/relocate sample TTL path | GPT-5.3-Codex | Medium |
| 1.3 | Real corpus→KG CI gate | GPT-5.4 | High |
| 2.1 | KG unquarantine checklist | GPT-5.4 | High |
| 2.2 | KG graduation decision | GPT-5.4 | High |
| 2.3 | KG pre-graduation implementation | GPT-5.3-Codex | High |
| 2.4 | KG post-graduation obligations | GPT-5.3-Codex | Medium |
| 3.1 | CLI registrar refactor | GPT-5.3-Codex | High |
| 3.2a | RAG retrieval boundary extraction | GPT-5.4 | High |
| 3.2b | RAG temporal/refusal policy extraction | GPT-5.4 | High |
| 3.2c | Provider/schema extraction | GPT-5.3-Codex | High |
| 3.2d | Slim API RAG route | GPT-5.3-Codex | Medium |
| 3.3 | Quarantine/archive misleading surfaces | GPT-5.3-Codex | Medium |
| 4.1 | Coverage gate | GPT-5.3-Codex | Medium |
| 4.2 | Latency/failure budgets | GPT-5.4 | High |
| 4.3 | Deployment/recovery story | GPT-5.4 | High |
| 4.4 | Lock single-host semantics | GPT-5.4 | Medium |
| 5.1 | Choose 7B production model | GPT-5.4 | Medium |
| 5.2 | Training data/contract prep | GPT-5.4 | High |
| 5.3 | First fine-tuning pass | GPT-5.3-Codex | High |
| 5.4 | Conservative model integration | GPT-5.4 | High |
| 6.1 | Benchmark plan after production model | GPT-5.4 | Medium |

---

## Practical next move
Start with **Tasks 1.1, 1.2, and 1.3 only**. That trio turns the project from “green but slightly theatrical” into “green for the path that actually matters.” After that, make the KG support decision with a clean table and a clean gate in hand.
