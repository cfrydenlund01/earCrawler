# Security Exposure Matrix

This document summarizes the current supported exposure boundaries for the
Windows-first EarCrawler deployment. It distinguishes network reachability from
request allowlists, because those are separate controls.

Use this as a quick reference for what is local-only, what may be published
through an approved front door, and what is still quarantined or optional.

| Surface | Endpoint / Port | Exposure in supported baseline | Control that enforces it | What it prevents | When it operates |
| --- | --- | --- | --- | --- | --- |
| Fuseki query service | `http://127.0.0.1:3030/ear/query` | Local-only | Loopback binding plus `--localhost` in `scripts/ops/windows-fuseki-service.ps1` and the operator contract in `docs/ops/windows_fuseki_operator.md` | Off-host network access to Fuseki in the supported baseline | At service install/startup and on every request because the listener never binds to a routable interface |
| EarCrawler API | `http://127.0.0.1:9001` | Local-only | Loopback binding in `scripts/ops/windows-single-host-service.ps1` and the operator contract in `docs/ops/windows_single_host_operator.md` | Direct remote exposure of the app process | At service install/startup and on every request because the listener never binds to a routable interface |
| IIS front door | HTTPS listener chosen by the operator, commonly `443` | Optional approved broader-exposure pattern only | Route allowlist plus reverse proxy configuration in `docs/ops/external_auth_front_door.md` and `scripts/ops/iis-earcrawler-front-door.web.config.example` | Unapproved paths, direct app exposure, and bypassing the edge auth layer | At request time, before traffic is forwarded to EarCrawler |
| SPARQL template execution | `/v1/sparql` | Supported API surface, but template-restricted | Allowlisted template execution in `service/docs/index.md` and `docs/api/readme.md` | Arbitrary SPARQL execution through the API | At request handling time inside the app |
| Text-index search | `/v1/search` | Quarantined | Runtime opt-in gates plus exclusion from default contract artifacts | Default-on search exposure and accidental promotion to baseline | At startup, contract generation, and request handling |

## Practical reading

- Fuseki on `3030` is safe in the supported baseline because it is bound to
  `127.0.0.1`, not because of an allowlist.
- EarCrawler on `9001` is safe for the same reason.
- The IIS allowlist is a publishing control, not a firewall. It limits which
  paths the proxy forwards, but it does not create network isolation by itself.
- The SPARQL allowlist is an application control. It limits which query
  templates can run, but it does not change network reachability.

## Support boundary

- Supported baseline: loopback-only API and loopback-only Fuseki.
- Approved broader exposure: IIS plus ARR plus Windows Authentication with a
  loopback backend hop.
- Not supported: exposing EarCrawler or Fuseki directly to a routed network
  with only `EARCRAWLER_API_KEYS`.

## Network security evidence in release validation

- Release validation now requires machine-readable security and observability
  evidence in addition to smoke tests:
  - `dist/security/security_scan_summary.json` (`ci-security-baseline.v1`)
  - `dist/observability/api_probe.json` (`api-probe-report.v1`)
- The observability probe evidence confirms loopback API health and readiness
  (`/health` returns `200`, readiness is `pass`, and latency stays within the
  configured budget).
- The installed-runtime smoke report remains the proof that release validation
  was executed in the single-host field-install shape, proved a healthy local
  read-only Fuseki dependency, and did not widen the supported network surface.

For the optional approved IIS front-door pattern, operators should also retain
the output of `scripts/ops/iis-front-door-smoke.ps1` so there is host-local
evidence that:

- the proxy, not the app listener, is the published network edge
- `X-Request-Id` survives the proxy hop for attribution
- unpublished routes such as quarantined `/v1/search` remain denied at the
  front door

## Operator network hardening checklist

- Keep EarCrawler bound to `127.0.0.1:9001` and Fuseki bound to
  `127.0.0.1:3030` in the supported baseline.
- Publish broader-than-loopback access only through the approved IIS front door
  pattern in `docs/ops/external_auth_front_door.md`.
- Keep host firewall policy aligned with the support boundary:
  - no direct routed-network inbound access to ports `9001` or `3030`
  - only the approved front-door listener (typically `443`) exposed when needed
