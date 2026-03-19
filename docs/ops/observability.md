# Observability & Health

This document summarises the monitoring signals introduced in B.23.

## Health Endpoints

* `GET /health` returns liveness + readiness information.
* Readiness aggregates Fuseki latency, template registry load, rate limiter
  state, and free disk space.
* `live_sources` reports live upstream-source freshness and degradation based on
  `data/manifest.json` (`upstream_status`) by default.
* JSON structure:

```json
{
  "status": "pass",
  "timestamp": "2025-02-01T12:00:00Z",
  "liveness": {"status": "pass"},
  "readiness": {
    "status": "pass",
    "checks": {
      "fuseki": {"status": "pass", "details": {"latency_ms": 85.2}},
      "templates": {"status": "pass", "details": {"templates": 3}},
      "rate_limiter": {"status": "pass", "details": {"limit": 120}},
      "disk": {"status": "pass", "details": {"free_mb": 1024}}
    }
  },
  "live_sources": {
    "status": "healthy",
    "manifest_path": "data/manifest.json",
    "stale_after_seconds": 86400,
    "summary": {"healthy": 2, "stale": 0, "degraded": 0, "unknown": 0}
  }
}
```

The budgets come from `service/config/observability.yml`.
`live_sources` defaults to `unknown` when the manifest is missing or does not
contain `upstream_status`.

## Structured Logs

* All requests produce a single JSON line with stable fields:
  `ts`, `level`, `service`, `event`, `trace_id`, `route`, `latency_ms`, `status`,
  and `details`.
* Sensitive material (emails, tokens, paths, query strings) is redacted.
* Logs are sampled via `request_logging.sample_rate` and truncated to
  `request_logging.max_details_bytes`.

## Windows Event Log Sink

* Summaries of warnings/errors are forwarded to the `EarCrawler` Event Log
  source when running on Windows.
* Register the source once: `scripts/eventlog/register-source.ps1` (requires
  elevation). Smoke tests can use `scripts/eventlog/test-event.ps1`.

## Probes & Canaries

* `scripts/health/fuseki-probe.ps1` validates Fuseki `/$/ping` and a
  deterministic `SELECT` query. Report saved to
  `kg/reports/health-fuseki.txt`.
* `scripts/health/api-probe.ps1` exercises supported `/health` readiness and
  latency budgets by default, then writes `kg/reports/health-api.txt`.
  When `-JsonReportPath` is provided it also writes a machine-readable
  `api-probe-report.v1` payload used by release validation (for example
  `dist/observability/api_probe.json`).
  For local validation only, pass `-IncludeQuarantinedSearch` to also probe
  quarantined `/v1/search`.
* `scripts/canary/run-canaries.ps1` loads `canary/config.yml`, executes the API
  and Fuseki checks, and writes JSON + text summaries to
  `kg/reports/canary-summary.json` and `.txt`. Non-zero exit signals budget
  breaches. The default canary config keeps API checks on supported routes.

## Watchdog

* `scripts/watchdog/watch-services.ps1` watches Fuseki + API PIDs. When either
  stops, it captures the last log lines, writes a timestamped report to
  `kg/reports/watchdog-<timestamp>.txt`, attempts restart via existing scripts,
  and emits an Event Log entry.
* Report creation is handled by `earCrawler.observability.watchdog` so tests can
  simulate failures without starting real processes.

## CI Wiring

`.github/workflows/kg-ci.yml` defines the `observability-health` job which:

1. Runs on `windows-latest` after the API surface job.
2. Registers the Event Log source (best-effort), starts Fuseki + API fixtures.
3. Runs both health probes and the canary runner.
4. Uploads `kg/reports/health-*.txt`, `canary-summary.*`, and watchdog reports.
5. Fails the build if probes or canaries fail their budgets.

All probes operate offline using deterministic requests and fixtures.
