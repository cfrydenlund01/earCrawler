# Retention policy

EarCrawler retains telemetry spools, HTTP caches, and knowledge-graph artifacts
under configurable limits. The default policies are:

| Target     | Max age (days) | Max total (MB) | Max file (MB) | Keep last |
|------------|----------------|----------------|---------------|-----------|
| telemetry  | 30             | 256            | 8             | 10        |
| cache      | 30             | 512            | 64            | 10        |
| kg         | 30             | 1024           | 256           | 10        |

Only paths under the whitelist are ever touched:
`kg/`, `.cache/api/`, `%APPDATA%\EarCrawler\spool`, and
`%PROGRAMDATA%\EarCrawler\spool`.

Run `earctl gc --dry-run --target all` to preview deletions. Use
`earctl gc --apply --target all --yes` to delete and write an audit log to
`kg/reports/gc-audit-<timestamp>.json`.

Telemetry spools can be cleared manually with `earctl telemetry purge`.
