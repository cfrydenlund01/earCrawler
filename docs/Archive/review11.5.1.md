# Review 11.5.1

Prepared: 2026-03-30  
Reviewer scope: document-only review  
Primary source: `docs/ExecutionPlan11.5_log.md`  
Archive sources reviewed:

- `docs/Archive/RunPass8.md`
- `docs/Archive/RunPass9.md`
- `docs/Archive/RunPass10.md`
- `docs/Archive/RunPass11.md`
- `docs/Archive/ExecutionPlanRunPass11.md`
- `docs/Archive/review_pass_7_step9_1_readiness_note.md`
- `docs/Archive/review_pass_7_step9_2_support_burden_analysis.md`
- `docs/Archive/review_pass_7_step9_4_alignment_summary.md`
- `docs/Archive/review_pass_8_step5_shared_rag_design.md`
- `docs/Archive/production_beta_readiness_review_2026-03-19.md`
- `docs/Archive/search_kg_quarantine_review_2026-03-19.md`

Constraint:

- This review intentionally analyzes only the logs/reviews/plans above.
- It does not claim direct source-code inspection beyond what those documents
  explicitly describe.

## Executive Summary

The network-facing history in the reviewed documents shows a clear pattern:

1. The repo repeatedly had real bugs around local network dependencies and
   upstream HTTP integrations, not just documentation drift.
2. ExecutionPlan 11.5 closed several important network/runtime defects:
   Federal Register fallback hangs, stale ORI pathing, Fuseki TDB2 startup
   mismatch, Fuseki dataset path mismatch, and search/KG production-like smoke
   coverage.
3. Two network-related risk areas still remain open in the reviewed
   documentation:
   - port/service lifecycle handling still appears operationally brittle
   - search and KG runtime behavior remain quarantined because the full
     installed-artifact/operator proof package is still incomplete

The net result is that the baseline network story is materially better than it
was in the archived passes, but another engineer should still treat the
FUSEKI/API/operator scripts and the upstream clients as the highest-risk
network surfaces in the repo.

## Findings

### 1. Medium: fixed localhost ports are used throughout the operator/runtime proof with no documentary evidence of collision preflight or recovery

Current evidence:

- `docs/ExecutionPlan11.5_log.md` repeatedly shows fixed port usage:
  - API on `127.0.0.1:9001`
  - Fuseki on `127.0.0.1:3030`
  - production-like search/KG smoke on `127.0.0.1:3040`
- The logs show start/stop commands and successful proofs, but they do not show
  explicit port-availability preflight, retry-on-collision logic, or
  deterministic conflict recovery.
- Another issue is that the port remained used, even when the process using the port was killed.

Why this matters:

- On a developer workstation or reused validation host, a stale API/Fuseki
  process can create false negatives that look like runtime defects but are
  actually port contention.
- This is especially relevant because the review history shows multiple
  manual/scripted local service launches rather than one centralized orchestrator.

Likely code/doc surfaces another engineer should inspect first:

- `scripts/api-start.ps1`
- `scripts/api-stop.ps1`
- `scripts/installed-runtime-smoke.ps1`
- `scripts/optional-runtime-smoke.ps1`
- `scripts/search-kg-prodlike-smoke.ps1`
- `scripts/ops/windows-fuseki-service.ps1`
- `scripts/health/api-probe.ps1`
- `scripts/health/fuseki-probe.ps1`

Status:

- Open risk in the documents reviewed.
- Not a confirmed code bug from docs alone, but strongly worth a code audit.

### 2. Medium: the Fuseki operator/runtime path had multiple real correctness bugs; 11.5 fixed them, but this remains the highest-risk local network dependency

Documented bugs closed in `docs/ExecutionPlan11.5_log.md`:

- installed-runtime smoke initially depended on behavior that broke under
  `unionDefaultGraph`; the fix was to load baseline fixture triples into a
  named graph in `scripts/installed-runtime-smoke.ps1`
- KG runtime proof exposed a TDB2 startup mismatch because `--tdb2` was not
  included in the Fuseki command
- `kg load --db db` and `kg serve --db db --dataset /ear` targeted different
  storage layouts, producing an empty served dataset under `/ear`
- Java version resolution differed by shell, causing local Fuseki automation to
  fail until `JAVA_HOME`/`PATH` were pinned

Files explicitly named in the logs:

- `earCrawler/kg/fuseki.py`
- `earCrawler/cli/kg_commands.py`
- `scripts/installed-runtime-smoke.ps1`
- `tests/kg/test_fuseki.py`
- `tests/cli/test_kg_emit_cli.py`

Why this matters:

- These are not abstract concerns. The reviewed docs show that the service
  could start and still serve the wrong dataset shape or return empty results.
- That makes Fuseki lifecycle and dataset-path handling the most important
  network-adjacent correctness area for another engineer to understand.

Status:

- Closed/fixed in 11.5 according to the logs.
- Still a high-priority regression surface.

### 3. Medium: upstream HTTP client behavior was previously ambiguous and failure-prone; 11.5 fixed real FR/ORI defects, but the broader failure taxonomy still deserves scrutiny

Documented failures:

- `docs/ExecutionPlan11.5_log.md` records ORI live ingest failing with HTTP 404
  because `api_clients/ori_client.py` targeted stale `/case_findings`
- the same log records EAR/Federal Register live ingest repeatedly timing out
  because the fallback path used recursive `_get_json` behavior and an invalid
  fallback query parameter (`conditions[any]` instead of `conditions[term]`)
- `docs/Archive/RunPass10.md` and `docs/Archive/RunPass11.md` both describe a
  broader architectural weakness where upstream failures can collapse into empty
  results or require side-channel status inspection

Files repeatedly implicated by the docs:

- `api_clients/federalregister_client.py`
- `api_clients/ori_client.py`
- `api_clients/tradegov_client.py`
- callers in `earCrawler/corpus/`
- health/reporting surfaces that publish live-source state

What 11.5 appears to have fixed:

- FR fallback recursion/hang behavior
- FR invalid fallback parameter behavior
- ORI stale listing path behavior
- at least some typed degraded-state exposure through manifests and `/health`

What still needs attention from the docs alone:

- the archive reviews repeatedly frame upstream failure semantics as a repo-wide
  issue, not just an FR/ORI issue
- the 11.5 log gives detailed closure for FR and ORI, but not the same level of
  narrative proof for Trade.gov failure taxonomy or caller behavior

Status:

- Partially closed, but still a likely audit target for another engineer.

### 4. Medium: search and KG runtime behavior are much better evidenced now, but still not promotable because the installed-artifact/operator network story remains incomplete

Historical path from the reviewed docs:

- `docs/Archive/RunPass8.md` and
  `docs/Archive/review_pass_7_step9_1_readiness_note.md` show that `/v1/search`
  was once a real route mounted in the API while quarantine was mostly
  documentary
- the same archive docs show observability, client, OpenAPI, and canary surfaces
  touching `/v1/search` even though the supported operator story excluded it
- `docs/Archive/review_pass_7_step9_4_alignment_summary.md` shows a later fix:
  default probes and canaries stopped implying supported status and
  quarantined-search checks became explicit opt-in
- `docs/ExecutionPlan11.5_log.md` then shows a stronger operator-owned proof
  package:
  - text-index validation mode in `scripts/ops/windows-fuseki-service.ps1`
  - optional text-query verification in `scripts/health/fuseki-probe.ps1`
  - new `scripts/search-kg-prodlike-smoke.ps1`
  - production-like search/KG proof recorded from `scripts/optional-runtime-smoke.ps1`

Why this is still open:

- `docs/ExecutionPlan11.5_log.md` Step 5.3 still ends in `Keep Quarantined`
- the stated blocker is not lack of implementation, but lack of full
  clean-room installed-artifact proof inside the signed release contract for
  those networked features
- `docs/Archive/search_kg_quarantine_review_2026-03-19.md` and
  `docs/Archive/review_pass_7_step9_2_support_burden_analysis.md` both make the
  same point: `/v1/search` and runtime KG expansion are support-costly because
  they require a full operator-owned text-indexed Fuseki story, rollback path,
  and release-shaped smoke proof

Status:

- Current unresolved network-support blocker.
- Not a baseline bug, but still a real operator/readiness gap.

### 5. Low-Medium: Java/runtime resolution remains a network-service startup hazard in local validation flows

Documented evidence:

- `docs/ExecutionPlan11.5_log.md` shows:
  - initial bootstrap verification failed on Java 8
  - installed-runtime smoke initially failed because a shell resolved Java 8
  - later search/KG proof required pinning `JAVA_HOME` to the repo-provided JDK 17
- the reviewed docs consistently tie local Fuseki startup correctness to Java
  resolution rather than only to Python code

Why this matters:

- The local network service can fail before it binds its port, even though the
  apparent problem is a script or runtime bootstrap issue rather than Fuseki
  itself.
- Another engineer reviewing port/open/close failures should treat Java
  resolution as part of the network-service lifecycle.

Status:

- Mostly mitigated by 11.5 doc/script alignment.
- Still worth preserving as operational context.

## Closed Bugs Worth Preserving In Context

These items appear closed in the reviewed logs, but they should remain in the
maintainer mental model because they directly affect network behavior.

### A. `/v1/search` support-boundary drift

Historical state from archive docs:

- route mounted
- client-visible
- OpenAPI-visible
- probed by canaries/observability
- not supported by the authoritative operator story

Documented later fix:

- default probe/canary/search helper behavior changed to supported routes only
- quarantined search became explicit opt-in

Key docs:

- `docs/Archive/RunPass8.md`
- `docs/Archive/review_pass_7_step9_1_readiness_note.md`
- `docs/Archive/review_pass_7_step9_4_alignment_summary.md`

### B. Fuseki returning the wrong runtime shape even when the service started

Historical defects recorded in 11.5:

- missing `--tdb2`
- `kg load` / `kg serve` storage-layout mismatch
- named-graph versus union-default-graph mismatch

Key docs:

- `docs/ExecutionPlan11.5_log.md`

### C. Upstream HTTP fetch hangs and stale endpoints

Historical defects recorded in 11.5:

- ORI stale path `/case_findings`
- FR fallback HTTP 400 due `conditions[any]`
- FR fallback recursion leading to amplified retry timing and hangs

Key docs:

- `docs/ExecutionPlan11.5_log.md`
- `docs/Archive/RunPass10.md`
- `docs/Archive/RunPass11.md`

## New or Changed Network-Related Code Called Out By The Logs

The following code/script surfaces are explicitly called out by the reviewed
docs as changed, newly added, or materially recoded in response to network or
service-runtime issues.

### Upstream HTTP ingestion/client changes

- `api_clients/federalregister_client.py`
- `api_clients/ori_client.py`
- `earCrawler/core/nsf_case_parser.py`
- `earCrawler/core/ear_crawler.py`
- `earCrawler/corpus/sources.py`

### Local API/Fuseki operator/runtime changes

- `earCrawler/kg/fuseki.py`
- `earCrawler/cli/kg_commands.py`
- `scripts/installed-runtime-smoke.ps1`
- `scripts/api-start.ps1`
- `scripts/api-smoke.ps1`
- `scripts/api-stop.ps1`
- `scripts/optional-runtime-smoke.ps1`
- `scripts/health/api-probe.ps1`
- `scripts/health/fuseki-probe.ps1`
- `scripts/ops/windows-fuseki-service.ps1`
- `scripts/search-kg-prodlike-smoke.ps1`

### Contract/observability alignment changes

- `docs/Archive/review_pass_7_step9_4_alignment_summary.md` points to:
  - `scripts/health/api-probe.ps1`
  - `canary/config.yml`
  - `scripts/api/curl_facade.ps1`
  - `docs/api/readme.md`
  - `docs/ops/observability.md`
  - `.env.example`

## Review Conclusions For A New Engineer

If another engineer picks this up cold, the most important document-derived
conclusions are:

1. The primary network risk is not generic HTTP routing. It is the combination
   of local Fuseki lifecycle, dataset-path correctness, Java resolution, and
   operator smoke orchestration.
2. The primary upstream-data risk is failure taxonomy and fallback correctness
   in `api_clients/*`, especially Federal Register and ORI.
3. Search and KG network features are implemented enough to look mature in
   logs, but the docs still keep them quarantined because the installed-artifact
   and operator rollback story is not fully closed.
4. Hard-coded localhost ports (`3030`, `3040`, `9001`) are pervasive in the
   reviewed logs; port collision handling should be one of the first things a
   new engineer checks in the scripts.
5. The reviewed docs show a real progression from documentary quarantine to
   runtime/observability alignment. That means historical archive notes should
   not be read as current truth without cross-checking `docs/ExecutionPlan11.5_log.md`.

## Recommended First Code Audit Based On This Review

Because this review is document-only, the next engineer should validate the
following code surfaces in this order:

1. `scripts/installed-runtime-smoke.ps1`
2. `earCrawler/kg/fuseki.py`
3. `earCrawler/cli/kg_commands.py`
4. `scripts/ops/windows-fuseki-service.ps1`
5. `scripts/search-kg-prodlike-smoke.ps1`
6. `scripts/optional-runtime-smoke.ps1`
7. `scripts/health/api-probe.ps1`
8. `scripts/health/fuseki-probe.ps1`
9. `api_clients/federalregister_client.py`
10. `api_clients/ori_client.py`
11. `api_clients/tradegov_client.py`

## Bottom Line

From the reviewed docs alone, the repo has already fixed multiple real
network/service bugs during ExecutionPlan 11.5. The remaining concerns are less
about missing code and more about operator reproducibility, port/service
lifecycle robustness, and the still-unfinished promotion story for search/KG
network features.
