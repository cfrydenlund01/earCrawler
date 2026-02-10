# Offline Snapshot Specification (v1)

## Goal
Make the “offline snapshot” a first-class, auditable input to corpus/index builds by:
- Defining an **authoritative payload format** (JSONL) and a **manifest** stored alongside it.
- Providing **acceptance criteria** that can be validated automatically (fail-fast).
- Making each build able to point to **one manifest** as the authoritative input for the run.

This spec covers the **eCFR offline snapshot** used to build the retrieval corpus (RAG).

## Ownership, Source, Cadence, Approval
### Source of truth
- Upstream: **eCFR** content for CFR Title(s) in scope (typically Title 15 for EAR).
- Snapshot payload is a **JSONL export** produced by the designated Snapshot Producer.

### Roles
- **Snapshot Producer (Owner)**: responsible for generating the payload + manifest and placing them in the approved storage location.
- **Snapshot Approver**: reviews the acceptance checklist and signs off that the snapshot is approved for use.

### Approved storage location (recommended)
- Store each snapshot as a **directory** containing the payload and manifest:
  - `.../<snapshot_id>/snapshot.jsonl`
  - `.../<snapshot_id>/manifest.json`

In this repo, the recommended layout is:
- `snapshots/offline/<snapshot_id>/snapshot.jsonl`
- `snapshots/offline/<snapshot_id>/manifest.json`

If you store the payload as a single file for local development (e.g., `data/ecfr/title15.jsonl`), store the manifest alongside it as either:
- `data/ecfr/manifest.json`, or
- `data/ecfr/title15.manifest.json`

### Update cadence (recommended)
- Default cadence: `monthly` (or `quarterly`), plus ad-hoc snapshots for critical regulatory changes.
- Approval cadence: every new `snapshot_id` requires an approval (no silent rolling updates).

### Approval record (recommended)
- Include the approver identity and approval timestamp in the manifest `source` block.
- The manifest hash binds the approval to the exact bytes used in the build.

## Snapshot Payload Format (JSONL)
File: `snapshot.jsonl` (UTF-8, LF-only newlines)

One JSON object per line, representing a CFR section:
```json
{"section_id":"§ 736.2","heading":"General prohibitions","text":"...","source_ref":"ecfr-2025-12-31","url":"https://..."}
```

### Required per-record fields
- `section_id`: string; MUST be normalizable to canonical EAR form (e.g., `EAR-736.2(b)`).
- `text`: string; MUST be non-empty after trimming whitespace.

### Optional per-record fields
- `heading`: string
- `url`: string
- `source_ref`: string (recommended; if omitted, the build should supply a `--source-ref` or the manifest should include one)

## Manifest Format (JSON)
File: `manifest.json` stored alongside the payload.

The manifest is the authoritative, auditable identity of the snapshot for a run.

### Required fields
- `manifest_version`: string; MUST equal `offline-snapshot.v1`.
- `snapshot_id`: string; unique stable identifier for the snapshot directory/run.
- `created_at`: string; ISO-8601 timestamp with timezone (recommend `Z`).
- `source`: object describing provenance and ownership (see below).
- `scope`: object declaring what the snapshot contains (titles/parts).
- `payload`: object describing the payload bytes (hash binds identity).

### `source` object (minimum)
- `owner`: string; human/team responsible for producing the snapshot.
- `upstream`: string; where it came from (e.g., `ecfr.gov API export`).
- `approved_by`: string; human/team that approved the snapshot for use.
- `approved_at`: string; ISO-8601 timestamp with timezone.

### `scope` object (minimum)
- `titles`: array of strings; non-empty (e.g., `["15"]`).
- `parts`: array of strings; REQUIRED (can be empty for full-title snapshots), e.g. `["730","732","734","736"]`.

### `payload` object (required)
- `path`: string; relative path from the manifest to the payload file (recommended: `snapshot.jsonl`).
- `sha256`: string; hex SHA-256 over the **raw payload bytes**.
- `size_bytes`: integer; size of the payload file in bytes.

## Acceptance Checklist (Fail-Fast)
An offline snapshot is acceptable only if all checks pass:
1. Manifest exists alongside the payload in an approved location.
2. Manifest required fields are present and correctly typed.
   - Includes `scope.titles` and `scope.parts`.
3. `payload.sha256` matches SHA-256 of the payload file bytes.
4. Payload encoding is stable:
   - UTF-8 (no BOM),
   - LF-only newlines (no CRLF).
5. Payload content is valid:
   - Every non-empty line is valid JSON object,
   - `section_id` is normalizable to canonical EAR id,
   - no duplicate canonical `section_id` values,
   - section `part` values align to manifest `scope.parts` when that list is non-empty,
   - `text` is not empty/whitespace.

## Storage Policy (Local vs External)
Storage mode: **(C) both**.

- **Committed (small dev-only snapshots):**
  - Keep tiny snapshots only under `tests/fixtures/` for unit tests and examples.
  - These are intentionally minimal and safe to commit.

- **Not committed (real snapshot payloads):**
  - Real snapshot payload files (`snapshot.jsonl`) are treated as external artifacts.
  - The repository may track the manifest, but must not track the payload.
  - `.gitignore` enforces this by ignoring snapshot payload paths.

- **Committed (manifest + hash):**
  - Manifests for approved snapshots MAY be committed under:
    - `snapshots/offline/<snapshot_id>/manifest.json`
  - Payloads live externally (shared drive/blob store), but must be fetched locally as a pair:
    - `snapshots/offline/<snapshot_id>/snapshot.jsonl`
    - `snapshots/offline/<snapshot_id>/manifest.json`

### Directory Layout (Recommended)
Authoritative per-snapshot directory:
- `snapshots/offline/<snapshot_id>/manifest.json` (tracked)
- `snapshots/offline/<snapshot_id>/snapshot.jsonl` (ignored, external)

### Reference Rule
- Builders and validators require the manifest to be co-located with the payload so the snapshot input for a run is unambiguous.

## Validation Entrypoint
Use the CLI before corpus/index work:
```powershell
py -m earCrawler.cli rag-index validate-snapshot --snapshot snapshots/offline/<snapshot_id>/snapshot.jsonl
```

Successful validation prints a short summary:
- section count
- title count
- payload bytes
- authoritative manifest path

## Self-Checks (Operational)
- One manifest can be named as “the authoritative snapshot for this run”.
- Any change to the payload bytes changes `payload.sha256` and therefore the run provenance.
- The contract is simple enough to validate automatically before building the corpus/index.
