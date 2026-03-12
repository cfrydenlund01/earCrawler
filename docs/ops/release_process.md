# Release Process

This document describes reproducible KG release steps.

1. Run `kg/scripts/canonical-freeze.ps1` to produce canonical files under `kg/canonical/`.
2. Create deterministic archive with `scripts/make-canonical-zip.ps1`.
3. Generate `manifest.json` and `checksums.sha256` via `scripts/make-manifest.ps1`.
4. Optionally sign the manifest using `scripts/sign-manifest.ps1` (requires secrets).
5. Validate wheel packaging from a clean-room venv outside the checkout:
   - `scripts/package-wheel-smoke.ps1 -WheelPath dist/earcrawler-*.whl`
6. Record provenance with `scripts/provenance-attest.ps1`.
7. Verify determinism: `scripts/rebuild-compare.ps1`.
8. Generate release checksums for distributable artifacts:
   - `scripts/checksums.ps1`
9. Use `scripts/verify-release.ps1` to validate canonical + distributable artifacts and emit evidence:
   - `scripts/verify-release.ps1 -RequireSignedExecutables -EvidenceOutPath dist/release_validation_evidence.json`
10. Archive `dist/release_validation_evidence.json` with the release bundle.

Single-host support note:
- Release evidence should always map to the supported deployment contract: one
  Windows host, one EarCrawler API service instance. Do not treat these steps
  as multi-instance runtime validation.

Environment variables:
- `SOURCE_DATE_EPOCH` – Unix timestamp used for fixed file times.
- `SIGNING_CERT_PFX_BASE64` and `SIGNING_CERT_PASSWORD` – optional signing material.
