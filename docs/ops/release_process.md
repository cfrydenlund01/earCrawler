# Release Process

This document describes reproducible KG release steps.

1. Run `kg/scripts/canonical-freeze.ps1` to produce canonical files under `kg/canonical/`.
2. Create deterministic archive with `scripts/make-canonical-zip.ps1`.
3. Generate `manifest.json` and `checksums.sha256` via `scripts/make-manifest.ps1`.
4. Optionally sign the manifest using `scripts/sign-manifest.ps1` (requires secrets).
5. Record provenance with `scripts/provenance-attest.ps1`.
6. Verify determinism: `scripts/rebuild-compare.ps1`.
7. Use `scripts/verify-release.ps1` to validate a downloaded release offline.

Environment variables:
- `SOURCE_DATE_EPOCH` – Unix timestamp used for fixed file times.
- `SIGNING_CERT_PFX_BASE64` and `SIGNING_CERT_PASSWORD` – optional signing material.
