# Release Process

This document describes reproducible KG release steps.

Local/CI preflight guard before deeper release work:
- `scripts/release-evidence-preflight.ps1 -AllowEmptyDist`
- fails fast when release-like files exist without `dist/checksums.sha256`, when `dist/checksums.sha256.sig` is missing, when checksums drift, or when uncontrolled top-level files sit next to the checksums file.

GitHub release promotion stages (`.github/workflows/release.yml`):
- `build`: produces signed distributables, checksums, canonical metadata, and `dist/promotion/build_stage_evidence.json`; uploads `release-build-stage`.
- `validate`: downloads `release-build-stage`, runs release security baseline plus smoke/verification gates, writes `dist/release_validation_evidence.json` and `dist/promotion/validation_stage_evidence.json`; uploads `release-validation-stage`.
- `promote`: downloads `release-validation-stage`, writes `dist/promotion/promotion_stage_evidence.json`, then publishes release assets.
- Each stage retains its evidence as both workflow artifacts and release files under `dist/promotion/*.json`.

1. Run `kg/scripts/canonical-freeze.ps1` to produce canonical files under `kg/canonical/`.
2. Create deterministic archive with `scripts/make-canonical-zip.ps1`.
3. Generate `manifest.json` and `checksums.sha256` via `scripts/make-manifest.ps1`.
4. Optionally sign the manifest using `scripts/sign-manifest.ps1` (supports env-provided PFX material or a cert already present in `Cert:\CurrentUser\My`).
5. Validate wheel packaging from a clean-room venv outside the checkout:
   - `scripts/package-wheel-smoke.ps1 -WheelPath dist/earcrawler-*.whl`
6. Build pinned Windows dependency wheelhouse:
   - `scripts/build-wheelhouse.ps1 -LockFile requirements-win-lock.txt`
7. Build the Windows executable:
   - `scripts/build-exe.ps1`
8. Build the Windows installer:
   - `scripts/make-installer.ps1`
9. Package hermetic install payload for operators:
   - include `requirements-win-lock.txt`, `.wheelhouse/`, and `scripts/install-from-wheelhouse.ps1` under `dist/hermetic-artifacts/`
   - zip as `dist/hermetic-artifacts.zip`
10. Sign executable artifacts and verify signatures when signing material is configured:
   - `scripts/sign-artifacts.ps1`
   - `signtool verify /pa dist/*.exe`
11. Generate release checksums for distributable artifacts:
   - `scripts/checksums.ps1`
   - `scripts/sign-manifest.ps1 -FilePath dist/checksums.sha256`
12. Run release security baseline evidence:
   - `scripts/security-baseline.ps1 -Python py -RequirementsLock requirements-win-lock.txt -PipAuditIgnoreFile security/pip_audit_ignore.txt -OutputDir dist/security`
13. Run installed-runtime smoke in the actual field-install artifact shape:
   - `scripts/installed-runtime-smoke.ps1 -WheelPath dist/earcrawler-*.whl -UseHermeticWheelhouse -HermeticBundleZipPath dist/hermetic-artifacts.zip -ReleaseChecksumsPath dist/checksums.sha256 -UseLiveFuseki -AutoProvisionFuseki -RequireFullBaseline -Host 127.0.0.1 -Port 9001 -ReportPath dist/installed_runtime_smoke.json`
   - this now provisions a temporary local read-only Fuseki dependency, validates Fuseki health, and proves the installed wheel against the supported API surface in the same single-host runtime shape
   - Java 17+ is required for the Fuseki auto-provision path
14. Run supported-path API smoke in the same release workspace shape and collect observability probe evidence:
   - `scripts/api-start.ps1 -Host 127.0.0.1 -Port 9001`
   - `scripts/api-smoke.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/api_smoke.json`
   - `scripts/health/api-probe.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/observability/health-api.txt -JsonReportPath dist/observability/api_probe.json`
   - `scripts/api-stop.ps1`
15. Run release-shaped optional-mode smoke coverage:
   - `scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -SkipLocalAdapter -ReportPath dist/optional_runtime_smoke.json`
16. Generate SBOM and canonical release metadata:
   - `scripts/sbom.ps1`
   - `kg/scripts/canonical-freeze.ps1`
   - `scripts/make-canonical-zip.ps1 -Version <tag>`
   - `scripts/make-manifest.ps1`
   - `scripts/sign-manifest.ps1`
   - `scripts/sign-manifest.ps1 -FilePath dist/checksums.sha256`
   - `scripts/provenance-attest.ps1`
   - `scripts/rebuild-compare.ps1 -Version <tag>`
17. Only if you are explicitly resuming the deprioritized local-adapter track documented in `docs/local_adapter_deprioritization_2026-03-25.md`, and a real Task 5.3 run artifact is available, produce the local-adapter evidence bundle:
   - `scripts/local_adapter_smoke.ps1 -RunDir dist/training/<run_id>`
   - `py -m scripts.eval.run_local_adapter_benchmark --run-dir dist/training/<run_id> --manifest eval/manifest.json --dataset-id ear_compliance.v2 --dataset-id entity_obligations.v2 --dataset-id unanswerable.v2 --smoke-report kg/reports/local-adapter-smoke.json`
   - `py -m scripts.eval.validate_local_adapter_release_bundle --run-dir dist/training/<run_id> --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json --smoke-report kg/reports/local-adapter-smoke.json`
18. Only if you are explicitly resuming the deprioritized local-adapter track documented in `docs/local_adapter_deprioritization_2026-03-25.md`, and a real Task 5.3 run artifact is available, run the same optional-runtime smoke with local-adapter validation:
   - `scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -LocalAdapterRunDir dist/training/<run_id> -ReportPath dist/optional_runtime_smoke.json`
19. Use `scripts/verify-release.ps1` to validate canonical + distributable artifacts and emit evidence:
   - `scripts/verify-release.ps1 -RequireSignedExecutables -RequireCompleteEvidence -ApiSmokeReportPath dist/api_smoke.json -OptionalRuntimeSmokeReportPath dist/optional_runtime_smoke.json -InstalledRuntimeSmokeReportPath dist/installed_runtime_smoke.json -SecuritySummaryPath dist/security/security_scan_summary.json -ObservabilityApiProbePath dist/observability/api_probe.json -EvidenceOutPath dist/release_validation_evidence.json`
   - validation now fails if any distributable output still includes files with `PLACEHOLDER` in the filename (for example `manifest.sig.PLACEHOLDER.txt` in `dist/offline_bundle/`)
   - validation now fails if `dist/checksums.sha256` does not cover every top-level release artifact present alongside it (except `checksums.sha256`, `checksums.sha256.sig`, and `release_validation_evidence.json`)
   - publication now also fails if the canonical manifest signature, release checksums signature, supported API smoke report, optional-runtime smoke report, installed-runtime smoke report, release security baseline summary, or observability API probe report are missing or non-passing
   - publication now also fails if installed-runtime smoke does not prove `install_mode = hermetic_wheelhouse`
   - publication now also fails if installed-runtime smoke does not prove `install_source = release_bundle`
20. Archive `dist/api_smoke.json`, `dist/installed_runtime_smoke.json`, `dist/release_validation_evidence.json`, `dist/optional_runtime_smoke.json`, `dist/security/*.json`, `dist/observability/api_probe.json`, `dist/observability/health-api.txt`, `dist/hermetic-artifacts.zip`, and `dist/promotion/*.json` with the release bundle.

Optional local-adapter note:
- A passing `release_evidence_manifest.json` keeps one named adapter candidate
  evidence-backed and reviewable, but it does not auto-promote the capability
  beyond `Optional`. Use `docs/local_adapter_release_evidence.md` for the exact
  decision rule.
- For the current production-beta target, the local-adapter track is formally
  deprioritized. Do not treat steps 17 and 18 as part of the normal release
  gate unless a later dated decision explicitly re-activates that work.

Single-host support note:
- Release evidence should always map to the supported deployment contract: one
  Windows host, one EarCrawler API service instance. Do not treat these steps
  as multi-instance runtime validation.

Environment variables:
- `SOURCE_DATE_EPOCH` - Unix timestamp used for fixed file times.
- `SIGNING_CERT_PFX_BASE64` and `SIGNING_CERT_PASSWORD` - optional PFX signing material.
- `SIGNING_THUMBPRINT` or `SIGNING_SUBJECT` - optional cert-store selector when signing with a certificate already installed in `Cert:\CurrentUser\My`.
