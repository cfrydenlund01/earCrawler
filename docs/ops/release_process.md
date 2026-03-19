# Release Process

This document describes reproducible KG release steps.

1. Run `kg/scripts/canonical-freeze.ps1` to produce canonical files under `kg/canonical/`.
2. Create deterministic archive with `scripts/make-canonical-zip.ps1`.
3. Generate `manifest.json` and `checksums.sha256` via `scripts/make-manifest.ps1`.
4. Optionally sign the manifest using `scripts/sign-manifest.ps1` (requires secrets).
5. Validate wheel packaging from a clean-room venv outside the checkout:
   - `scripts/package-wheel-smoke.ps1 -WheelPath dist/earcrawler-*.whl`
6. Run installed-runtime smoke from the built wheel in a clean-room venv:
   - `scripts/installed-runtime-smoke.ps1 -WheelPath dist/earcrawler-*.whl -Host 127.0.0.1 -Port 9001 -ReportPath dist/installed_runtime_smoke.json`
7. Record provenance with `scripts/provenance-attest.ps1`.
8. Verify determinism: `scripts/rebuild-compare.ps1`.
9. Generate release checksums for distributable artifacts:
   - `scripts/checksums.ps1`
10. Run supported-path API smoke in the same release workspace shape:
   - `scripts/api-start.ps1 -Host 127.0.0.1 -Port 9001`
   - `scripts/api-smoke.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/api_smoke.json`
   - `scripts/api-stop.ps1`
11. Run release-shaped optional-mode smoke coverage:
   - `scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -SkipLocalAdapter -ReportPath dist/optional_runtime_smoke.json`
12. If a real Task 5.3 run artifact is available, run the same smoke with local-adapter validation:
   - `scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -LocalAdapterRunDir dist/training/<run_id> -ReportPath dist/optional_runtime_smoke.json`
13. Use `scripts/verify-release.ps1` to validate canonical + distributable artifacts and emit evidence:
   - `scripts/verify-release.ps1 -RequireSignedExecutables -RequireCompleteEvidence -ApiSmokeReportPath dist/api_smoke.json -OptionalRuntimeSmokeReportPath dist/optional_runtime_smoke.json -InstalledRuntimeSmokeReportPath dist/installed_runtime_smoke.json -EvidenceOutPath dist/release_validation_evidence.json`
   - validation now fails if any distributable output still includes files with `PLACEHOLDER` in the filename (for example `manifest.sig.PLACEHOLDER.txt` in `dist/offline_bundle/`)
   - publication now also fails if the canonical manifest signature, release checksums signature, supported API smoke report, optional-runtime smoke report, or installed-runtime smoke report are missing or non-passing
14. Archive `dist/api_smoke.json`, `dist/installed_runtime_smoke.json`, `dist/release_validation_evidence.json`, and `dist/optional_runtime_smoke.json` with the release bundle.

Single-host support note:
- Release evidence should always map to the supported deployment contract: one
  Windows host, one EarCrawler API service instance. Do not treat these steps
  as multi-instance runtime validation.

Environment variables:
- `SOURCE_DATE_EPOCH` - Unix timestamp used for fixed file times.
- `SIGNING_CERT_PFX_BASE64` and `SIGNING_CERT_PASSWORD` - optional signing material.
