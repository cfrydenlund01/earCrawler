# Redaction Rules

The telemetry subsystem removes sensitive data before it is written to disk or sent over the network.

* Email addresses – `/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/`
* Bearer tokens or secrets – `/[A-Za-z0-9\-_=]{20,}/`
* File paths – replaced with `[path]`
* URLs with query strings – query portion stripped
* GUIDs – `/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/`
* Environment values matching `*_KEY`, `*_TOKEN`, or `*_SECRET` are removed if present in strings.

Only the following keys are ever stored: `command`, `duration_ms`, `exit_code`, `version`, `os`, `python`, `device_id`, `event`, `ts`, and `error` when present.
