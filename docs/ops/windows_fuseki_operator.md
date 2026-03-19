# Windows Fuseki Operator Guide

This document is the authoritative operator handoff for the supported Fuseki
dependency used by the Windows single-host EarCrawler deployment. It covers the
supported read-only query service only:

- Apache Jena Fuseki `5.3.0`
- one Windows host
- one local read-only Fuseki instance
- one dataset service at `http://127.0.0.1:3030/ear/query`

Use this guide together with `docs/ops/windows_single_host_operator.md`. Bring
Fuseki up first, verify it, then start the EarCrawler API service.

## Scope and support boundary

- Supported deployment shape: one loopback-bound Fuseki service on the same
  Windows host as the EarCrawler API service.
- Supported endpoint contract: read-only SPARQL query service at
  `/ear/query`.
- Supported persistence: local TDB2 dataset under
  `C:\ProgramData\EarCrawler\fuseki\databases\tdb2`.
- Supported management wrapper: NSSM (`nssm.exe`) running the pinned Fuseki
  launcher.
- Not part of the supported baseline:
  - text-index-backed Fuseki provisioning
  - `/v1/search`
  - KG expansion promotion
  - multi-host or internet-facing Fuseki exposure

This guide does not unquarantine search or KG-backed runtime behavior. It
operationalizes the baseline read-only query dependency only.

## Pinned version

Pinned tool versions are recorded in `tools/versions.json`:

- Apache Jena: `5.3.0`
- Apache Jena Fuseki: `5.3.0`

Treat those pins as authoritative for the supported baseline unless a later
release intentionally updates them.

## Standard host layout

| Path | Purpose |
| --- | --- |
| `C:\Program Files\Apache\Jena-5.3.0` | Pinned Jena tool install root |
| `C:\Program Files\Apache\Jena-Fuseki-5.3.0` | Pinned Fuseki install root |
| `C:\ProgramData\EarCrawler\fuseki\config` | Service config, including the generated read-only assembler |
| `C:\ProgramData\EarCrawler\fuseki\databases\tdb2` | TDB2 dataset files |
| `C:\ProgramData\EarCrawler\fuseki\logs` | Fuseki stdout/stderr logs |
| `C:\ProgramData\EarCrawler\backups\fuseki` | Fuseki backup snapshots |

## Required inputs

Before provisioning the host, collect:

- Java 11 or newer installed and available to the service account
- NSSM installed on the host
- Apache Jena `5.3.0` zip from the official Apache distribution
- Apache Jena Fuseki `5.3.0` zip from the official Apache distribution
- the release KG dataset artifact to load into TDB2, preferably N-Quads
  (`dataset.nq`) when available
- the EarCrawler API wheel and the API operator guide

## Fresh provision

### 1. Install the pinned Jena and Fuseki binaries

Extract Apache Jena `5.3.0` and Apache Jena Fuseki `5.3.0` into the standard install roots:

```powershell
$jenaHome = 'C:\Program Files\Apache\Jena-5.3.0'
$fusekiHome = 'C:\Program Files\Apache\Jena-Fuseki-5.3.0'
New-Item -ItemType Directory -Force -Path $jenaHome, $fusekiHome | Out-Null
# Extract apache-jena-5.3.0.zip into $jenaHome
# Extract apache-jena-fuseki-5.3.0.zip into $fusekiHome
```

Verify the required launchers exist:

```powershell
Test-Path 'C:\Program Files\Apache\Jena-5.3.0\bat\tdb2_tdbloader.bat'
Test-Path 'C:\Program Files\Apache\Jena-Fuseki-5.3.0\fuseki-server.bat'
```

### 2. Render the supported read-only config and install the service

The supported automation lives under `scripts/ops/`:

- `scripts/ops/windows-fuseki-service.ps1`
- `scripts/ops/windows-fuseki-backup.ps1`
- `scripts/ops/windows-fuseki-restore-drill.ps1`
- `scripts/health/fuseki-probe.ps1`

Install the service and generate the read-only assembler:

```powershell
pwsh scripts/ops/windows-fuseki-service.ps1 `
  -Action install `
  -NssmPath C:\tools\nssm\nssm.exe `
  -FusekiHome 'C:\Program Files\Apache\Jena-Fuseki-5.3.0' `
  -ProgramDataRoot 'C:\ProgramData\EarCrawler\fuseki' `
  -FusekiHost 127.0.0.1 `
  -FusekiPort 3030 `
  -DatasetName ear
```

This creates:

- `C:\ProgramData\EarCrawler\fuseki\config\tdb2-readonly-query.ttl`
- `C:\ProgramData\EarCrawler\fuseki\databases\tdb2`
- `C:\ProgramData\EarCrawler\fuseki\logs`
- the `EarCrawler-Fuseki` Windows service

The generated config exposes only the supported read-only query endpoint:

- `http://127.0.0.1:3030/ear/query`

It does not enable text indexing or any search-specific service surface.

### 3. Load the released dataset into TDB2

Load the approved dataset artifact before starting the API service. Prefer an
N-Quads release artifact when available:

```powershell
& 'C:\Program Files\Apache\Jena-5.3.0\bat\tdb2_tdbloader.bat' `
  --loc 'C:\ProgramData\EarCrawler\fuseki\databases\tdb2' `
  'C:\path\to\dataset.nq'
```

If the release artifact is Turtle instead of N-Quads:

```powershell
& 'C:\Program Files\Apache\Jena-5.3.0\bat\tdb2_tdbloader.bat' `
  --loc 'C:\ProgramData\EarCrawler\fuseki\databases\tdb2' `
  'C:\path\to\ear.ttl'
```

Only load reviewed release artifacts. Do not point the supported host at ad hoc
research datasets.

### 4. Start and verify Fuseki

```powershell
pwsh scripts/ops/windows-fuseki-service.ps1 -Action start
pwsh scripts/ops/windows-fuseki-service.ps1 -Action health
pwsh scripts/ops/windows-fuseki-service.ps1 -Action status
```

Healthy install criteria:

- `Get-Service EarCrawler-Fuseki` reports `Running`
- `scripts/health/fuseki-probe.ps1` passes
- `http://127.0.0.1:3030/$/ping` returns HTTP 200
- `http://127.0.0.1:3030/ear/query` returns HTTP 200 for a trivial query

Recommended direct probe:

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:3030/ear/query `
  -Method Post `
  -ContentType 'application/sparql-query' `
  -Body 'SELECT (1 AS ?ok) WHERE { } LIMIT 1' `
  -UseBasicParsing
```

### 5. Start the EarCrawler API after Fuseki is healthy

After Fuseki is healthy, continue with
`docs/ops/windows_single_host_operator.md`:

1. set `EARCRAWLER_FUSEKI_URL=http://127.0.0.1:3030/ear/query`
2. start the `EarCrawler-API` service
3. verify `/health`

## Startup order

Use this sequence for every boot, restore, and upgrade window:

1. Ensure the TDB2 dataset is present or restored.
2. Start `EarCrawler-Fuseki`.
3. Run `scripts/ops/windows-fuseki-service.ps1 -Action health`.
4. Start `EarCrawler-API`.
5. Verify `http://127.0.0.1:9001/health`.

If Fuseki is unavailable, do not treat the API service as healthy even if the
process itself starts.

## Health checks

The supported Fuseki health check is `scripts/health/fuseki-probe.ps1`. It
verifies:

- loopback `/$/ping`
- a trivial SPARQL query against the configured query endpoint
- latency against the budgets in `service/config/observability.yml`

Run it directly:

```powershell
pwsh scripts/health/fuseki-probe.ps1 `
  -FusekiUrl http://127.0.0.1:3030/ear/query `
  -ReportPath C:\ProgramData\EarCrawler\fuseki\logs\health-fuseki.txt
```

## Backup

Take a Fuseki backup before every upgrade and before any manual TDB2 repair.
Stop the EarCrawler API first so no queries are in flight during the backup
window.

Preferred path:

```powershell
pwsh scripts/ops/windows-single-host-service.ps1 -Action stop
pwsh scripts/ops/windows-fuseki-backup.ps1 `
  -ProgramDataRoot 'C:\ProgramData\EarCrawler\fuseki' `
  -FusekiHome 'C:\Program Files\Apache\Jena-Fuseki-5.3.0' `
  -BackupRoot 'C:\ProgramData\EarCrawler\backups\fuseki' `
  -RestartServiceAfterBackup
pwsh scripts/ops/windows-single-host-service.ps1 -Action start
```

The backup snapshot includes:

- `config`
- `databases`
- `logs`
- service metadata (`service-qc.txt`, `service-failure.txt`)
- captured machine environment export
- `java-version.txt`
- `snapshot_manifest.json`
- `checksums.sha256`

Treat the backup as valid only when `snapshot_manifest.json` and
`checksums.sha256` are present.

## Restore

Restore is for host loss, storage corruption, or operator error.

1. Stop `EarCrawler-API`.
2. Stop `EarCrawler-Fuseki`.
3. Reinstall the pinned Fuseki binaries if the host was rebuilt.
4. Restore the latest reviewed backup snapshot under
   `C:\ProgramData\EarCrawler\fuseki`.
5. Reinstall or verify the NSSM service definition.
6. Start Fuseki and run the health probe.
7. Start the EarCrawler API and verify `/health`.

Non-destructive restore drill:

```powershell
pwsh scripts/ops/windows-fuseki-restore-drill.ps1 `
  -SnapshotPath 'C:\ProgramData\EarCrawler\backups\fuseki\<snapshot-id>' `
  -DrillRoot 'C:\ProgramData\EarCrawler\backups\fuseki\drills\<snapshot-id>'
```

Treat a failing drill report as a deployment blocker.

For recurring host-level DR evidence (API + Fuseki together), use:

```powershell
pwsh scripts/ops/windows-recurring-dr-evidence.ps1 `
  -ProgramDataRoot 'C:\ProgramData\EarCrawler' `
  -FusekiProgramDataRoot 'C:\ProgramData\EarCrawler\fuseki' `
  -FusekiHome 'C:\Program Files\Apache\Jena-Fuseki-5.3.0' `
  -FusekiBackupRoot 'C:\ProgramData\EarCrawler\backups\fuseki' `
  -EvidenceRoot 'C:\ProgramData\EarCrawler\backups\recurring-evidence' `
  -RetentionRuns 30 `
  -SkipServiceControl
```

## Upgrade

The supported baseline is pinned to Fuseki `5.3.0`. Upgrades are controlled
maintenance events, not routine drift.

Upgrade procedure:

1. Stop `EarCrawler-API`.
2. Take a fresh Fuseki backup snapshot.
3. Stop `EarCrawler-Fuseki`.
4. Extract the new reviewed Fuseki version side-by-side under a versioned
   install path.
5. Re-run `scripts/ops/windows-fuseki-service.ps1 -Action install` with the new
   `-FusekiHome`.
6. Start Fuseki and run the health probe.
7. Start the EarCrawler API and verify `/health`.

If health fails after the upgrade:

1. stop both services
2. reinstall the prior known-good Fuseki version
3. restore the last good snapshot if the dataset was touched
4. start Fuseki, then the API, and verify both health checks

## Failure signatures

| Symptom | Likely cause | Operator action |
| --- | --- | --- |
| `/$/ping` connection refused or timeout | Fuseki service is stopped, hung, or bound to the wrong port | Check `Get-Service EarCrawler-Fuseki`, review `C:\ProgramData\EarCrawler\fuseki\logs\fuseki-service.log`, confirm port `3030` is free |
| `/ear/query` returns `404` | Wrong dataset name or wrong assembler config | Re-render config with `windows-fuseki-service.ps1 -Action render-config`, verify service path is `/ear/query`, then restart |
| `/ear/query` returns `500` on trivial `SELECT` | TDB2 store is missing, damaged, or locked | Stop the service, inspect the dataset directory, and restore the latest good snapshot if needed |
| Startup fails with Java errors | `JAVA_HOME` missing or incompatible Java runtime | Reinstall or repair Java 11+, confirm the service account can run `java -version` |
| `Address already in use` in Fuseki logs | Port collision on `3030` | Stop the conflicting process or move Fuseki to a reviewed alternate port and update `EARCRAWLER_FUSEKI_URL` accordingly |
| EarCrawler API `/health` reports Fuseki errors after API startup | Startup order was wrong or `EARCRAWLER_FUSEKI_URL` does not match the local service | Fix Fuseki first, then restart the API after the health probe passes |

## Proven vs documented vs future automation

What is now proven in-repo:

- the supported Fuseki pin (`5.3.0`) is recorded in `tools/versions.json`
- a repeatable read-only service config can be rendered by
  `scripts/ops/windows-fuseki-service.ps1`
- Fuseki health checks run through `scripts/health/fuseki-probe.ps1`
- backup snapshots and restore drills have dedicated automation

What is documented but still operator-executed:

- Java installation and host prerequisites
- initial TDB2 load from a reviewed release dataset artifact
- side-by-side Fuseki binary upgrades

What still needs future automation:

- clean-room release smoke that provisions a fresh local Fuseki host end-to-end
- automated verification of backup/restore on a schedule
- host-side download and checksum verification of Fuseki without relying on a
  source checkout or separately staged archive





