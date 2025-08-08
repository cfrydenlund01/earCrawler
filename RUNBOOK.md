# Runbook

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
