# Telemetry Policy

EarCrawler collects minimal, pseudonymous usage data only when telemetry is explicitly enabled. By default telemetry is disabled. When enabled, events such as command name, duration, exit code, application version, and operating system are written to a local spool directory and may be uploaded to a configured endpoint.

No API payloads, document text, file contents, or secrets are collected. Email addresses, tokens, file paths, and query strings are redacted before leaving the process. A random UUID is used as the device identifier.

Retention is limited by spool size and age; old files are automatically removed. Telemetry can be disabled or purged at any time using the `earctl telemetry` commands.
