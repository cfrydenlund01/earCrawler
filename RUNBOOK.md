# Runbook

## Testing
- Default offline run: `py -m pytest -q` (network marked tests are excluded by default).
- Finetune/GPU suite (opt-in): `set EARCRAWLER_ENABLE_GPU_TESTS=1` then `py -m pytest -q -m finetune` (requires CUDA).
- Network-marked tests: `py -m pytest -q -m network` when outbound access is explicitly allowed.
- Torch and GPU tests skip automatically if PyTorch is missing or fails to load (ImportError/OSError/DLL errors).

## Release packaging
1. Bump version in `pyproject.toml` and commit.
2. Tag `vX.Y.Z` and push.
3. Ensure signing secrets `SIGNING_CERT_PFX_BASE64` and `SIGNING_CERT_PASSWORD` are available when signing.
4. Run `pwsh scripts/build-wheel.ps1`, `pwsh scripts/build-exe.ps1`, and `pwsh scripts/make-installer.ps1`.
5. Run `pwsh scripts/sign-artifacts.ps1` to sign executables and installer.
6. Verify locally with `signtool verify /pa dist\earctl-*.exe` and `signtool verify /pa dist\earcrawler-setup-*.exe`.
7. Generate checksums and SBOM with `pwsh scripts/checksums.ps1` and `pwsh scripts/sbom.ps1`.
8. Create a GitHub release and upload the wheel, EXE, installer, checksum, and SBOM files.

Windows notes
- Inno Setup (iscc.exe): install via winget if not present.
  - `set PATH=%LOCALAPPDATA%\\Microsoft\\WindowsApps;%PATH%`
  - `winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements`
  - If `iscc.exe` is not on PATH after install, invoke directly:
    - `%LOCALAPPDATA%\\Programs\\Inno Setup 6\\ISCC.exe installer\\earcrawler.iss`
- The installer script writes output to `dist\\` (configured in `installer/earcrawler.iss`).
- `scripts/make-installer.ps1` exports `EARCRAWLER_VERSION` automatically; no manual env prep needed.

## Deploying Containers
1. Tag a release: `git tag vX.Y.Z && git push origin vX.Y.Z`.
2. GitHub Actions builds and pushes `api` and `rag` images to GHCR.
3. On the host, pull images:
   - `docker pull ghcr.io/<org>/earCrawler/api:vX.Y.Z`
   - `docker pull ghcr.io/<org>/earCrawler/rag:vX.Y.Z`
4. Restart services with `docker compose up -d`.

## Rollback
1. Locate previous stable tag.
2. Pull prior images using that tag.
3. Redeploy containers with the older tag.
4. Run `monitor.ps1` to verify `/health` endpoints report `ok`.

## Secret Rotation
- API keys and SPARQL URLs are stored in Windows Credential Manager or as environment variables.
- Rotate a credential:
  1. `cmdkey /delete:TRADEGOV_API_KEY`
  2. `cmdkey /generic:TRADEGOV_API_KEY /user:ignored /pass:<NEW_VALUE>`
- For environment variables, update deployment configuration and restart containers.

## Telemetry Operations
- Enable or disable with `earctl telemetry enable|disable`.
- Change the upload endpoint by editing `%APPDATA%\EarCrawler\telemetry.json`.
- Rotate the HTTP auth token stored in the Windows Credential Manager under the name specified by `auth_secret_name` in the config.
- Force garbage collection of the spool by deleting old `events-*.jsonl.gz` files or running `scripts/telemetry-gc.ps1`.

## Scheduled Jobs & Admin Runs
- CLI entry point: `py -m earCrawler.cli jobs run {tradegov|federalregister} [--dry-run] [--quiet]`. Pair `--dry-run` with CI or smoke checks; omit it for live ingests.
- PowerShell wrappers for Task Scheduler live under `scripts/jobs/run_tradegov_ingest.ps1` and `scripts/jobs/run_federalregister_anchor.ps1`. They handle logging folders and status codes for Windows-first deployments.
- Each invocation emits structured logs plus a JSON run summary (`run_id`, `steps`, `durations`, `status`) under `run/logs/`. Archive these artifacts for operator review and attach them to CI uploads when possible.

## Export Profiles
- Generate export bundles with `py -m earCrawler.cli bundle export-profiles --ttl kg/ear.ttl --out dist/exports --stem dataset`.
- Expected outputs: `dist/exports/dataset.ttl`, `dataset.nt`, and gzip variants, alongside `manifest.json` and `checksums.sha256`.
- Ensure the manifest and checksum files stay in sync with the emitted Turtle/N-Triples. CI should fail fast if hashes drift.

## Integrity Gate
- Validate graph integrity before export or load via `py -m earCrawler.cli integrity check <ttl>`.
- Any non-zero violation counters cause the command to exit with a failure code; treat this as a hard stop for downstream export, load, or deployment stages.
- Typical violations include missing provenance links, namespace drift, or orphaned part nodes-inspect the emitted report to trace the offending triples.

## Evaluation datasets & schema
- Location: evaluation JSONL files live under `eval/` and are indexed by `eval/manifest.json`. The manifest records:
  - `kg_state.digest`: the KG snapshot hash from `kg/.kgstate/manifest.json` that the datasets were curated against.
  - `datasets[]`: entries with `id` (e.g. `ear_compliance.v1`), `task` (e.g. `ear_compliance`, `entity_obligation`, `unanswerable`), `file`, `version`, `description`, and `num_items`.
- Referential references: the manifest also includes `references.sections`, `references.kg_nodes`, and `references.kg_paths`. These lists describe the curated EAR sections and KG policy nodes that the evaluation slices cover. `python eval/validate_datasets.py` checks both the JSON schema *and* that every `doc_spans` and `kg_nodes` reference maps to these curated entries before CI passes.
- Per-item JSONL schema (one object per line):
  - `id` (string) – stable item identifier.
  - `task` (string) – logical task name (`ear_compliance`, `entity_obligation`, `unanswerable`, etc.).
  - `question` (string) – user-facing question text.
  - `ground_truth` (object):
    - `answer_text` (string) – canonical short answer.
    - `label` (string) – normalized label (`license_required`, `no_license_required`, `permitted`, `permitted_with_license`, `prohibited`, `unanswerable`, etc.).
  - `ear_sections` (array of strings) – EAR section IDs that determine the answer (for example `["EAR-744.6(b)(3)"]`).
  - `kg_entities` (array of strings) – IRIs of the main KG entities involved (for example `["https://example.org/ear#entity/acme"]`), or empty when the item is purely statute-level.
  - `evidence` (object):
    - `doc_spans` (array) – items of the form `{ "doc_id": "<EAR document ID>", "span_id": "<section/paragraph ID>" }` that should be sufficient to justify the answer.
    - `kg_nodes` (array of strings) – IRIs of policy-graph nodes (obligations, exceptions) that encode the decision logic.
    - `kg_paths` (optional array of strings) – identifiers for precomputed reasoning paths used in explainability/graph-walk evaluations.
- The evaluation harness expects exactly this shape and treats unknown extra keys as opaque; keep the schema stable when adding new datasets and bump the dataset `id`/`version` when you need to change semantics.
- CLI helpers:
  - Run `python eval/validate_datasets.py` locally (or watch CI) to catch schema or referential errors early.
  - `py -m earCrawler.cli eval run-rag --dataset-id <id>` writes metrics to `dist/eval/<id>.rag.<provider>.<model>.json` and Markdown summaries to `dist/eval/<id>.rag.<provider>.<model>.md`. Remote calls are gated by `EARCRAWLER_ENABLE_REMOTE_LLM=1` and provider API keys.
  - `python scripts/eval/log_eval_summary.py dist/eval/*.json` prints a markdown-ready bullet list that can be pasted into `Research/decision_log.md` when logging Phase E endpoints.

## Toolchain maintenance

### Rotating Jena/Fuseki versions
1. Update `tools/versions.json` with the new version and SHA512 from the official `.sha512` files.
2. Run `pwsh scripts/verify-java-tools.ps1` to download and verify the archives.

### Regenerating lockfiles with hashes
1. Modify `requirements.in` or `requirements-win.in` as needed.
2. `pip-compile --generate-hashes requirements.in -o requirements-lock.txt`
3. `pip-compile --generate-hashes requirements-win.in -o requirements-win-lock.txt`
4. Rebuild the wheelhouse: `pwsh scripts/build-wheelhouse.ps1`
- To share data with support, run `scripts/telemetry-export.ps1` which bundles recent events into `dist/telemetry_bundle.jsonl.gz` after an additional redaction pass.

## Monitoring
Execute `./monitor.ps1 -Services @('http://localhost:8000/health')` to poll services.
Failures are written to `monitor.log` and the Windows Event Log under source `EARMonitor`.

## NSF Case Parsing
Use offline fixtures to parse ORI misconduct cases. Live mode is disabled by
default to keep CI deterministic.

```cmd
python -m earCrawler.cli nsf-parse --fixtures tests/fixtures --out data --live false
```

The command writes one JSON file per case into the `data` directory. Supply
`--live` to fetch fresh listings when networking is permitted.

## Unified Crawl
Run the corpus loaders via the CLI:

```cmd
python -m earCrawler.cli crawl --sources ear nsf
```

Only the Trade.gov API key is required; the Federal Register API is public.

## Corpus Pipeline
Use the Windows `py` launcher so paths resolve correctly on PowerShell:

1. Build deterministically from fixtures (no network):  
   `py -m earCrawler.cli corpus build -s ear -s nsf --out data --fixtures tests/fixtures`
2. Validate provenance fields before emitting downstream files:  
   `py -m earCrawler.cli corpus validate --dir data`
3. Snapshot artifacts for operators or CI logs:  
   `py -m earCrawler.cli corpus snapshot --dir data --out dist/corpus`

- Use `--live` during scheduled jobs to hit production sources; fixture runs keep CI deterministic.
- Outputs land under `data\*_corpus.jsonl`, `data\manifest.json`, and `data\checksums.sha256` and are stable across reruns with the same inputs.
- These commands require the `operator` (or `maintainer`) role defined in `security\policy.yml`; set `EARCTL_USER=test_operator` during local testing if needed.
- Routine verification (byte-for-byte determinism + provenance validation) is enforced by `scripts/ci-corpus-determinism.ps1` and runs in CI.
  - Local: `pwsh scripts/ci-corpus-determinism.ps1`

## Reporting
Generate analytics over stored corpora:

```cmd
python -m earCrawler.cli report --sources ear nsf --type top-entities --entity ORG
```

Use `--out report.json` to save the results to a file.

## Phase B: Knowledge Graph

### Ontology
Classes: `ear:Reg`, `ear:Section`, `ear:Paragraph`, `ear:Citation`, `ent:Entity`

Properties: `ear:hasSection`, `ear:hasParagraph`, `ear:cites`, `dct:source`, `dct:issued`, `prov:wasDerivedFrom`

### Versioning & exports
- Schema and SHACL shapes are frozen at **v1.0.0** (`earCrawler.kg.ontology.KG_SCHEMA_VERSION`) with matching metadata embedded at the head of `earCrawler/kg/shapes.ttl` and `earCrawler/kg/shapes_prov.ttl`.
- Deterministic export hashes for `kg/ear.ttl` live in `kg/ear_export_manifest.json`. Regenerate with `py -m earCrawler.cli bundle export-profiles --ttl kg/ear.ttl --out dist/exports --stem ear` and update the manifest intentionally when the ontology changes.

### Phase B Baseline Freeze & Drift Gate
- The canonical KG baseline is tracked under `kg/baseline` (dataset + SRJ snapshots + manifest/checksums). It is intentionally minimal to avoid large binaries while still detecting KG drift.
- Baseline regeneration is deterministic given the same inputs and `SOURCE_DATE_EPOCH` (default `946684800`).
- CI enforces no drift by rebuilding the baseline and running `git diff --exit-code -- kg/baseline`, plus a separate determinism check that rebuilds twice.

Regenerate/update the baseline intentionally:
```powershell
pwsh kg/scripts/phase-b-freeze.ps1
git diff -- kg/baseline
```

Verify the baseline is locked (no drift):
```powershell
pwsh kg/scripts/phase-b-freeze.ps1
git diff --exit-code -- kg/baseline
```

Run the determinism check locally:
```powershell
pwsh scripts/rebuild-compare.ps1 -Version ci
```

### Warmers & budgets
- `perf/warmers/warm_queries.json` primes lookup, aggregation, and join query groups (each query carries a `# @group` comment).
- Run `pwsh kg/scripts/cache-warm.ps1` against a Fuseki endpoint before collecting performance reports so that the budgets in `perf/config/perf_budgets.yml` see warm caches.

```
Reg --hasSection--> Section --hasParagraph--> Paragraph
Paragraph --cites--> Citation
Paragraph <-prov:wasDerivedFrom- Entity
```

### End-to-end (offline)
```cmd
python -m earCrawler.cli crawl --sources ear nsf
python -m earCrawler.cli kg-emit -s ear -s nsf -i data -o data\kg
python -m earCrawler.cli kg-load --ttl data\kg\ear.ttl --db db
```

### Troubleshooting on Windows
- If port 3030 is in use, start Fuseki with `--port 3031`.
- Exclude your `db\` directory from Windows Defender to avoid file locks.
- FileNotFoundError -> earCrawler now auto-installs Jena; ensure your session has network access on first run.

## Jena bootstrap

Local commands download the Apache Jena **5.3.0** Windows binary distribution to
`tools\jena` on first use. The bootstrap prefers the Apache archive and falls
back to the live mirror. Set `JENA_VERSION` to override the pin. The extracted
folder must contain `bat\` scripts such as `riot.bat`, `arq.bat`, and one of
`tdb2_tdbloader.bat`/`tdb2.tdbloader.bat`.
- If Defender blocks extraction, try running PowerShell as Administrator or exclude the repo folder temporarily.

# Phase B.2
Use `kg-load` to ingest triples into TDB2.
## Phase B.3 — Serve & Query
```cmd
# Serve (foreground)
python -m earCrawler.cli kg-serve -d db -p 3030 --dataset /ear

# Dry run (print command)
python -m earCrawler.cli kg-serve --dry-run

# Query (SELECT)
python -m earCrawler.cli kg-query --sparql "SELECT * WHERE { ?s ?p ?o } LIMIT 5" -o data\rows.json

# Query (CONSTRUCT)
python -m earCrawler.cli kg-query --form construct -q "CONSTRUCT WHERE { ?s ?p ?o } LIMIT 10" -o data\graph.nt
```

Stop the server with `Ctrl+C` in the console. For programmatic use, the
``running_fuseki`` context manager in ``earCrawler.kg.fuseki`` ensures cleanup.

## Validation Troubleshooting

| Violation | Fix |
| --- | --- |
| missing_provenance | Ensure the source JSONL has `source_url`, `prov:wasDerivedFrom`, and `date` fields. |
| entity_mentions_without_type | Regenerate TTL ensuring each entity node is typed `ent:Entity`. |

## B.6 Round-trip CI
- `.github/workflows/kg-ci.yml` runs `kg/scripts/ci-roundtrip.ps1` on Windows to
  validate TTL, round-trip through TDB2, capture SPARQL snapshots, and smoke-test
  Fuseki.
- If a snapshot diff fails, inspect the `.srj.actual` file, update the expected
  snapshot under `kg/snapshots`, and re-run the script.
- The isomorphism fallback is implemented in `kg/tools/GraphIsoCheck.java` and
  is compiled on-the-fly when a textual diff is detected.
## B.7 SHACL/OWL smoke
- `kg/scripts/ci-shacl-owl.ps1` runs SHACL validation against `kg/shapes.ttl` and executes three OWL reasoner ASK queries.
- Reports are written to `kg/reports/`.
- `shacl-conforms.txt` of `false` indicates shape violations; inspect `shacl-report.ttl` or `.json`.
- Failed OWL checks appear in `owl-smoke.json` with `passed: false`.
- CI job `shacl-owl-smoke` runs after the round-trip step and uploads reports even on failure.

## B.8 Inference service
### Assembler anatomy
`kg/assembler/tdb2-inference-*.ttl` wraps a TDB2 dataset under `kg/target/tdb2` with a `ja:InfModel` and publishes a Fuseki service `/ds-inf` with a `/sparql` endpoint. The RDFS config uses `RDFSRuleReasonerFactory` while the OWL Mini variant uses `OWLMiniReasonerFactory`.

### Switching modes
Start Fuseki with the desired assembler:

```powershell
fuseki-server.bat --config kg/assembler/tdb2-inference-rdfs.ttl   # RDFS
fuseki-server.bat --config kg/assembler/tdb2-inference-owlmini.ttl # OWL Mini
```

Run the smoke script to load TTLs, boot the server, and execute remote queries:

```powershell
pwsh kg/scripts/ci-inference-smoke.ps1 -Mode rdfs
pwsh kg/scripts/ci-inference-smoke.ps1 -Mode owlmini
```

### Troubleshooting
- **Server won't start:** ensure `tools/jena` and `tools/fuseki` exist and no other process is using port 3030.
- **ASK check fails:** verify all TTL files (excluding `shapes.ttl`) and the `testdata/reasoner_smoke.ttl` fixture loaded into `kg/target/tdb2`.
- **Empty SELECT report:** check that inference mode matches expectations and queries reference the correct namespace.

## API contract tests
- Cassettes live under `tests/fixtures/cassettes`. To refresh them, run tests with
  `VCR_RECORD_MODE=once` so new HTTP interactions are recorded.
- Commit updated cassette files after verifying fields.
- If contract tests drift, compare failing cassettes with live responses and
  adjust normalization logic or update fixtures.

## Provenance checks
- `kg/scripts/ci-provenance.ps1` validates `kg/prov/prov.ttl`, loads the domain
  and provenance graphs into TDB2, and executes lineage SPARQL queries.
- Reports under `kg/reports/lineage-*.{srj,txt}` summarise missing provenance and
activity integrity.
- A non-zero count or `true` ASK result indicates broken lineage links. Re-run
emitters with `new_prov_graph()` to regenerate provenance.

## Incremental KG builds
- The first run of `kg/scripts/ci-incremental.ps1` creates a manifest of hashed
  inputs. Subsequent runs compare hashes and skip rebuilds when unchanged.
- To force a rebuild, delete `kg/.kgstate/manifest.json` or run with
  `STRICT_SNAPSHOT=1`.
- Review `kg/reports/diff-summary.txt` for a human-friendly list of snapshot
  diffs. Ordering issues typically stem from missing `ORDER BY` clauses in
  queries.

## Retention and GC
- Preview deletions with `earctl gc --dry-run --target all`.
- Apply with `earctl gc --apply --target all --yes`; audit logs appear under
  `kg/reports/`.
- Schedule automatic weekly GC via `scripts/schedule-gc.ps1`, which registers
  a Task Scheduler job named `EarCrawler-GC`.
- Adjust defaults in `earCrawler/telemetry/config.py` or override with CLI
  flags.
- Inspect `kg/reports/gc-report.json` to review results.
