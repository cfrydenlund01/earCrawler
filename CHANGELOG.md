## [0.23.0]
### Added
- Health endpoints with readiness subchecks and Windows-focused probes.
- Structured JSON request logging with optional Windows Event Log sink.
- Canary scripts, watchdog restarts, and CI observability gating.

## [0.22.0]
### Added
- Read-only HTTP API facade with rate limiting, request budgets, and RBAC-aware start/stop commands.
- OpenAPI 3.1 specification, templated SPARQL registry, and structured problem details.
- Windows service wrapper documentation and smoke-test scripts for CI.

## [0.20.0]
### Added
- Performance tuning, query budgets, cache warmers, and regression gates.

## [0.19.0]
### Added
- RBAC and tamper-evident audit ledger with Windows Credential Manager enforcement.

## [0.18.0]
### Added
- Deterministic reconciliation with thresholds, conflict reports and CI gates.

## [0.17.0]
### Added
- Scheduled monitoring and delta ingest with automated pull requests.

## [0.16.0]
### Added
- Reproducible KG snapshot releases with signed manifest and provenance.

## [0.15.0]
### Added
- Hermetic toolchain with Jena/Fuseki checksum verification.
- Hash-locked Python dependencies and offline wheelhouse installer.
- CycloneDX SBOM generation and attestation script.

## [0.14.0]
### Added
- Centralised retention GC for telemetry, caches, and KG artifacts.
- Telemetry timestamps now use timezone-aware UTC with ISO-8601 `Z`.
- CI job runs GC in dry-run mode and uploads reports.

## [0.12.0]
### Added
- Windows packaging: CLI entrypoint `earctl`, PyInstaller executable, Inno Setup installer, signed artifacts, checksums, SBOM, and release workflow.

## [0.11.0]
### Added
- Incremental KG builds with content hashing, change detection, and diff snapshots.

## [0.10.0]
### Added
- PROV-O provenance for API data with deterministic IRIs.
- SHACL shapes enforcing minimal provenance.
- Lineage SPARQL checks wired into Windows CI.

## [0.9.0] - 2025-08-12
### Added
- SPARQL sanity checks and SHACL validation (`kg-validate`) for EAR/NSF TTLs.
- Windows-first CI smoke tests for emit + validate.
- Trade.gov and Federal Register clients with HTTP caching.
- VCR recorded fixtures and offline API contract tests.
- KG enrichment helpers and CLI commands.

## [0.8.0]
### Added
- feat(kg): ontology + TTL emitters for EAR/NSF with deterministic output; CLI `kg-emit`

## [0.7.0]
### Added
- feat(kg): add Fuseki serve (kg-serve) and SPARQL query (kg-query) commands
- feat(kg): Windows-first absolute invocation of local Jena (auto-download)
- test(kg): offline tests for Fuseki launcher and SPARQL client
- docs(kg): README/RUNBOOK updates with Windows examples

## [0.6.1]
### Added
- feat(kg): auto-install Apache Jena into tools/jena and invoke TDB2 loader by absolute path on Windows
- docs(kg): update README/RUNBOOK for zero-setup loading
### Fixed
- fix(bootstrap): archive-first Jena 5.3.0 download with Windows bat validation and unified version pin

## [0.6.0]
### Added
- feat(kg): add kg-load CLI and loader module for Jena TDB2 import

## [0.5.0]
### Added
- feat(analytics): add cross-corpus reporting CLI and analytics module
- feat(kg): add TTL exporter, ontology skeleton, and kg-export CLI command
- chore(windows): add Jena env checker script and Java live-export pre-check

## [0.4.0]
### Added
- Offline NSF/ORI case parser with deterministic hashing and entity extraction.
- CLI ``nsf-parse`` command and ORI client scaffold.
- Unit tests with offline HTML fixtures.
- Documentation updates and Windows CI workflow running ``pytest``.
- Unified ``CorpusLoader`` with EAR and NSF loaders and ``crawl`` CLI command.
- Federal Register client no longer requires an API key.
- Trade.gov client can read API key from environment variables.

## [0.2.0]
### Added
- CI hardening: lint, coverage threshold, GPU matrix, secrets management.

## [0.1.0] – 2025-06-25
### Added
- Scaffolded `api_clients` modules for Trade.gov and Federal Register APIs.
- Unit tests in `tests/` with mocking and error-handling checks.
- GitHub Actions CI workflow targeting `windows-latest`.
- Comprehensive `README.md` with Windows setup instructions.
- Implement Trade.gov API client with paging, error handling, and pytest suite. [#VERSION]
- Add Federal Register API client for EAR text retrieval with pagination, error handling, and pytest suite. [#VERSION]
- Add core crawler orchestration to fetch entities and documents for ingestion. [#VERSION]
- Add ETL ingestion script with SHACL validation and Jena TDB2 loading. [#VERSION]
- Add FastAPI-based SPARQL query service for TDB2 data. [#VERSION]
- Add analytics ReportsGenerator module for SPARQL-based aggregate reporting. [#VERSION]
- Add CLI for fetching analytics reports via FastAPI service. [#VERSION]
- Package earCrawler as installable CLI with console-script entry-point (v0.1.0).
- Implement RAG Retriever using all-MiniLM-L12-v2 and FAISS. [#VERSION]
- Add FastAPI KG service with safe SPARQL query and SHACL-validated inserts. [#VERSION]
- Add Legal-BERT fine-tuning using PEFT/LoRA adapters. [#VERSION]
- Add Mistral-7B QLoRA instruction-tuned agent with LoRA adapters. [#VERSION]
- Add end-to-end benchmark script integrating LoRA and QLoRA components. [#VERSION]
- Finalize production Docker images and monitoring for LoRA/QLoRA pipeline. [#VERSION]

v0.6.0 – B.6: RIOT validation, TDB2 round-trip with isomorphism fallback, deterministic SPARQL snapshots, Fuseki smoke query, Windows CI, and pytest smoke tests.
v0.7.0 – B.7: SHACL validation, OWL reasoner smoke checks, Windows CI job, and pytest coverage.
v0.8.0 – B.8: Fuseki assembler inference service, RDFS/OWL Mini modes, Windows CI smoke, and tests.
v0.18.0 – Deterministic reconciliation with thresholds, conflict reports, and CI gates.
