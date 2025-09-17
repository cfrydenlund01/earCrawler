# Offline Bundle Usage Guide

This document describes how to work with the portable offline bundle produced by
`earctl bundle build`. The bundle is designed for Windows-first environments and
keeps all execution local so it can run on networks without Internet access.

## Preparing the bundle

1. Run `earctl bundle build` on a machine that already has the canonical KG
   artifacts under `kg/canonical`.
2. Copy `dist/offline_bundle/` to the target machine. When distributing the
   bundle externally, zip the directory with deterministic timestamps
   (`SOURCE_DATE_EPOCH`) and publish a detached signature for
   `checksums.sha256`.
3. Review `README_OFFLINE.md` inside the bundle for a condensed quick-start.

## Verifying integrity

On the target machine open PowerShell and run:

```powershell
cd path\to\offline_bundle
scripts\bundle-verify.ps1
```

The script recomputes SHA256 digests for every file listed in
`checksums.sha256`. It also warns about unexpected files or missing entries. The
bundle should not be modified before verification. Signature validation is
performed separately using the instructions in `manifest.sig.PLACEHOLDER.txt`.

## First run bootstrap

`bundle-first-run.ps1` performs the heavy lifting required for first use:

* Validates that Java, Apache Jena, and Apache Jena Fuseki are installed under
  `tools/` (created by the hermetic bootstrap scripts from B.15).
* Runs `scripts/bundle-verify.ps1` to ensure the payload is intact.
* Loads the canonical dataset (`kg/dataset.nq`) into a read-only TDB2 store at
  `fuseki/databases/tdb2` using `tdb2_tdbloader.bat`.
* Starts the Fuseki server with the read-only `/ds` service and executes a
  health probe plus a sample SPARQL query.
* Stops the server and writes `fuseki/databases/first_run.ok` along with a smoke
  report at `kg/reports/bundle-smoke.txt`.

The script is idempotent. If `first_run.ok` already exists it skips the loading
step and just performs verification and health checks.

## Operating the server

After the first run the bundle can be started or stopped with:

```powershell
scripts\bundle-start.ps1
scripts\bundle-stop.ps1
```

`bundle-start.ps1` blocks until the `/ds` endpoint responds to `/$/ping` and a
`SELECT` query. `bundle-health.ps1` can be used independently for periodic
checks while the server is running.

To stop the server run `scripts\bundle-stop.ps1`. It reads the PID recorded by
`bundle-start.ps1`, sends a termination signal, and removes the PID file once
shutdown completes.

## Upgrading to a new release

1. Run `earctl bundle build` on a trusted machine.
2. Verify the new bundle with `scripts\bundle-verify.ps1`.
3. Stop the existing Fuseki instance.
4. Replace the old bundle directory with the freshly built one.
5. Run `scripts\bundle-first-run.ps1` to perform a sanity check.

Previous smoke reports remain in `kg/reports/`. Garbage collection retains
recent bundles for 90 days (see `earctl gc`).
