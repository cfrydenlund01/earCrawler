# Windows Service Configuration Pointer

Use `docs/ops/windows_single_host_operator.md` for the supported Windows
single-host service configuration.

That guide is the source of truth for:

- the ASGI entrypoint `service.api_server.server:app`
- the standard host directory layout
- required environment variables
- NSSM runtime configuration
- service-account and restart expectations
- upgrade, backup, restore, rollback, and secret rotation

This file intentionally avoids carrying a second copy of the operator
configuration.
