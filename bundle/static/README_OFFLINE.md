# Offline bundle quick start

Welcome! This directory is a portable, read-only copy of the EarCrawler
knowledge graph plus helper scripts. Follow these steps on the first run:

1. Verify integrity with `scripts\bundle-verify.ps1`.
2. Run `scripts\bundle-first-run.ps1` to validate the toolchain, load the TDB2
   database, and execute smoke checks.
3. Start the read-only Fuseki endpoint with `scripts\bundle-start.ps1`.
4. When finished, stop the server using `scripts\bundle-stop.ps1`.

Additional documentation lives in `docs/offline_bundle/usage.md` within the
source repository. To create a deterministic ZIP, use an external archiver with
`SOURCE_DATE_EPOCH` set and keep all timestamps fixed.
