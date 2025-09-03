# Runbook

## Release packaging
1. Bump version in `pyproject.toml` and commit.
2. Tag `vX.Y.Z` and push.
3. Ensure signing secrets `SIGNING_CERT_PFX_BASE64` and `SIGNING_CERT_PASSWORD` are available when signing.
4. Run `pwsh scripts/build-wheel.ps1`, `pwsh scripts/build-exe.ps1`, and `pwsh scripts/make-installer.ps1`.
5. Run `pwsh scripts/sign-artifacts.ps1` to sign executables and installer.
6. Verify locally with `signtool verify /pa dist\earctl-*.exe` and `signtool verify /pa dist\earcrawler-setup-*.exe`.
7. Generate checksums and SBOM with `pwsh scripts/checksums.ps1` and `pwsh scripts/sbom.ps1`.
8. Create a GitHub release and upload the wheel, EXE, installer, checksum, and SBOM files.

## Deploying LoRA/QLoRA Models
1. Tag a release: `git tag vX.Y.Z && git push origin vX.Y.Z`.
2. GitHub Actions builds and pushes `api`, `rag`, and `agent` images to GHCR.
3. On the host, pull images:
   - `docker pull ghcr.io/<org>/earCrawler/api:vX.Y.Z`
   - `docker pull ghcr.io/<org>/earCrawler/rag:vX.Y.Z`
   - `docker pull ghcr.io/<org>/earCrawler/agent:vX.Y.Z`
4. Mount adapter weights or model artifacts into the container under `models/`.
5. Restart services with `docker compose up -d`.

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
