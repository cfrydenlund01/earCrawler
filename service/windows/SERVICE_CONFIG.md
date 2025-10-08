# EarCrawler API Windows Service Configuration

* **Service name**: `EarCrawler-API`
* **Executable**: `python.exe -m uvicorn service.api_server.server:app`
* **Working directory**: Repository checkout root (e.g. `C:\Apps\EarCrawler`).
* **Port**: Default 9001 (set with `EARCRAWLER_API_PORT`).
* **Fuseki endpoint**: `EARCRAWLER_FUSEKI_URL` (e.g. `http://localhost:3030/dataset/query`).
* **Rate limits**: Tuned via environment variables `EARCRAWLER_API_ANON_PER_MIN`,
  `EARCRAWLER_API_AUTH_PER_MIN`, and `EARCRAWLER_API_BURST`.
* **Logging**: Redirect stdout/stderr to
  `C:\ProgramData\EarCrawler\logs\api-service.log`. Structured JSON logs
  include `trace_id`, `identity`, and rate-limit counters.
* **Recovery**: Enable automatic restart on failure (after 15 seconds) and
  configure three restart attempts via the Windows Service Manager.
* **Firewall**: Allow inbound TCP traffic on the configured port for
  `EarCrawler-API` host IPs only.
* **Service account**: Run as a domain service account with least privilege.
  Grant `Log on as a service`, read access to the repository, and permissions to
  read API keys from the Windows Credential Manager.
