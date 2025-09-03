# Provenance Format

The `provenance.json` file records build metadata for reproducibility.

Fields:
- `git_commit`: commit hash used for the build.
- `manifest_sha256`: SHA256 digest of `manifest.json`.
- `run_id`: CI workflow run identifier.
- `runner_os`: operating system of the builder.
- `tool_versions_sha256`: hash of `tools/versions.json`.
- `build_timestamp`: UTC time of the build in ISO-8601 `Z` format.

Verify by recomputing file hashes and comparing fields to expected values.
