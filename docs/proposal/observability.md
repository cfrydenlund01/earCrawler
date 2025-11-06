# Observability & SLOs

## Signals
- **Logging**: Structured JSON logs via `earCrawler.utils.log_json.JsonLogger`.
  API facade attaches request metadata, trace IDs, and sampling controls
  (see `service/api_server/logging_integration.py`).
- **Metrics**: Rate limiting and concurrency counters exposed via
  `service/api_server/limits.py`. Fuseki health monitored through canary
  queries (`canary/config.yml`).
- **Tracing**: Request context middleware seeds per-request trace IDs for
  downstream correlation (`service/api_server/middleware.py`).

## Service Level Objectives
- **API availability**: 99.5% success rate for `/health` and `/v1/search`
  within <800 ms P95 latency (mirrors canary thresholds).
- **SPARQL latency**: 95% of SELECT queries under 1.5 s.
- **Ingestion freshness**: New EAR / NSF content available in KG within
  6 hours of publication (tracked via audit ledger + bundle timestamps).

## Canary Coverage
- `monitor.ps1` polls `/health` and `/v1/search`.
- `canary/config.yml` executes SPARQL ASK/SELECT drills against Fuseki.
- Integrate with Task Scheduler or Azure Automation to run every 5 minutes;
  emit to Windows Event Log (`monitor.ps1`) for SOC integration.

## Dashboards & Alerting
- Export logs to your SIEM via Windows Event Forwarding:
  - API logs -> Event source `EarCrawler.Api`.
  - Fuseki logs -> `tools/fuseki/logs/*.log`.
- Recommended alerts:
  1. API availability SLO breach (>0.5% failures in 1 hour).
  2. SPARQL latency P95 > 1.5 s for 3 consecutive windows.
  3. Ingestion lag > 6 hours (compare latest paragraph timestamp with audit ledger).

## Runbook References
- Release + rollback flows: `RUNBOOK.md`.
- Telemetry operations: `RUNBOOK.md` & `earCrawler/telemetry/hooks.py`.
- Incident response: attach `demo/SUMMARY.txt` output and `monitor.log` when
  filing tickets to ensure reproducibility of ingestion + export steps.
