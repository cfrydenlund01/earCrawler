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
