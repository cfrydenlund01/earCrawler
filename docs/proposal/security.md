# Security & Compliance Overview

## Secrets & Credentials
- Production CLI and services read secrets from the Windows Credential
  Manager (`earCrawler.utils.secure_store`, `api_clients/*`). Configure the
  following entries before live runs:
  - `TRADEGOV_API_KEY` – Trade.gov CSL key.
  - `FEDERALREGISTER_USER_AGENT` – Identifies the crawler to api.federalregister.gov.
  - `EAR_API_TOKEN` (optional) – Facade bearer token.
- System installs can be overridden with environment variables for container
  deployments (`EARCRAWLER_FUSEKI_URL`, `EARCRAWLER_API_KEY` etc). Never
  commit raw secrets—`secure_store.get_secret` centralises lookup logic.

## Role-Based Access Control
- CLI roles and command permissions live in `security/policy.yml`. Defaults:
  - `reader`: read-only (`diagnose`, `policy`, `report`).
  - `operator`: corpus movement, bundle, GC.
  - `maintainer`: reconcile, release, admin workflows.
  - `admin`: full access.
- Local operator workflows set `EARCTL_USER=test_operator`. Production runs
  rely on Windows account identity; see `earCrawler/security/identity.py`.
- Policy enforcement is wired through `earCrawler/security/policy.enforce`
  and emits audit events for both approvals and denials.

## Audit & Provenance
- Command executions append structured entries to `audit/ledger.py`
  (`run/logs/*.jsonl`). Each record includes actor, roles, command, args
  (post-redaction), duration, and success flag.
- Knowledge-graph exports embed provenance with `PROV.wasDerivedFrom` and
  optional response hashes. `earCrawler/kg/emit_ear.py` and `emit_nsf.py`
  share the redaction pipeline.

## Data Protection & Telemetry
- Telemetry defaults to disabled; enabling writes to `%APPDATA%\EarCrawler`.
  Configuration is versioned in `earCrawler/telemetry/config.py`.
- Redaction rules live under `docs/privacy/redaction_rules.md` and are applied
  in `earCrawler/telemetry/redaction.py`.
- Deleting or rotating telemetry artefacts is handled via
  `earctl telemetry gc` or direct file removal (`RUNBOOK.md`).

## Compliance Controls
- SBOM (`bundle/static/SBOM.cdx.json`) and NOTICE file support third-party
  disclosure requirements; rebuild via `pwsh scripts/build-release.ps1`.
- Perf budgets and Fuseki tuning are codified in `perf/config/*.yml`;
  tightening budgets or adjusting concurrency must be reviewed with the
  export control officer per proposal Section 5.
