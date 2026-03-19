# External Auth Front-Door Pattern

This document defines the approved integration pattern for any deployment broader
than the supported trusted single-host baseline.

It does not replace the supported baseline in
`docs/ops/windows_single_host_operator.md`. The supported baseline remains:

- one Windows host
- one EarCrawler API service instance
- loopback binding (`127.0.0.1`/`localhost`)
- static shared-secret API auth or anonymous lower-quota mode

Use this document only when a deployment must accept traffic from beyond the
local trusted host boundary.

## Status and support boundary

- Supported baseline: direct loopback/single-host access per
  `docs/ops/windows_single_host_operator.md`.
- Approved broader-exposure pattern: keep EarCrawler bound to loopback and put
  an operator-managed reverse proxy or API gateway in front of it.
- Not approved: exposing the EarCrawler process directly to a routed network or
  the public internet with only `EARCRAWLER_API_KEYS`.
- Not approved: teaching the EarCrawler app to trust identity headers from
  arbitrary clients.

The current app-level auth model is a static shared secret. That is acceptable
for the supported single-host posture, but it is not a sufficient enterprise
front door by itself.

## Approved deployment shape

The broader-exposure pattern is:

1. Keep EarCrawler listening only on `127.0.0.1` or another host-local-only
   interface.
2. Place a reverse proxy or API gateway in front of it.
3. Terminate TLS and user or workload authentication at that front door.
4. Enforce coarse authorization, IP allowlisting, and rate controls at that
   front door.
5. Have the proxy call EarCrawler over loopback using a deployment-owned
   backend credential in `X-Api-Key`.

Reference shape:

```text
client -> TLS/authz reverse proxy -> loopback EarCrawler API -> local Fuseki
```

Examples of acceptable front doors include IIS with Windows auth, nginx,
Apache httpd, or an enterprise API gateway, provided the controls below are
implemented.

## Approved reference deployment

The approved reference pattern for this repository is:

- IIS on the same Windows host as EarCrawler
- IIS Application Request Routing (ARR) plus URL Rewrite
- Windows Integrated Authentication at the IIS site or virtual directory
- EarCrawler still bound only to `127.0.0.1`
- one deployment-owned backend `X-Api-Key` injected by IIS on the loopback hop

Reference shape:

```text
domain user -> HTTPS IIS site (Windows auth + allowlist) -> ARR reverse proxy -> http://127.0.0.1:9001 -> local Fuseki
```

Reference assets:

- example IIS config: `scripts/ops/iis-earcrawler-front-door.web.config.example`
- baseline app hosting guide: `docs/ops/windows_single_host_operator.md`

This is the one concrete pattern operators should copy first when they need
broader-than-loopback access without changing the app's internal auth model.

### Why IIS is the reference

This repository's supported operator story is Windows-first, already assumes a
single-host service wrapper, and already uses machine-scoped secrets and local
host layout conventions. IIS with ARR fits that story with the least new moving
parts for a Windows operator team.

Other reverse proxies can still be acceptable, but they are not the reference
pattern this repo documents in detail.

## IIS reference shape

Use the IIS pattern as follows:

1. Install and validate the supported EarCrawler service exactly as documented in
   `docs/ops/windows_single_host_operator.md`.
2. Keep the EarCrawler listener on `127.0.0.1:9001`.
3. Install IIS, URL Rewrite, and ARR on the same host.
4. Publish only the IIS listener to the routed network.
5. Enable Windows Authentication at the IIS site and disable anonymous access
   unless a separate edge system is intentionally handling authentication in
   front of IIS.
6. Restrict access to the approved AD users or groups at IIS.
7. Configure ARR to proxy only the supported EarCrawler routes to
   `http://127.0.0.1:9001`.
8. Inject the deployment-owned backend `X-Api-Key` on the IIS to EarCrawler hop.
9. Log the authenticated Windows principal, source IP, IIS request id or trace
   fields, and the EarCrawler response `X-Request-Id`.

Do not expose Uvicorn directly on a non-loopback address and then treat IIS as
optional defense in depth. In this pattern IIS is the network edge and
EarCrawler remains a loopback-only backend.

## Identity expectations

The external front door, not the EarCrawler app, is responsible for authenticating:

- human users
- service accounts
- upstream workloads

Acceptable identity systems include:

- Windows Integrated Authentication / Active Directory
- OIDC or SAML SSO at the reverse proxy or gateway
- mTLS-authenticated service identities

EarCrawler currently resolves only:

- `X-Api-Key` for authenticated app access
- client IP for anonymous access

Because of that, the proxy must not assume EarCrawler will perform per-user
authorization or persist end-user identity as the authoritative audit subject.
The proxy authenticates the caller, then presents one deployment-owned backend
credential to EarCrawler.

For the IIS reference pattern, the expected external identity is an AD-backed
Windows principal validated by IIS. Group-based authorization belongs at IIS,
not in EarCrawler.

## Backend credential pattern

Use a dedicated backend API key label for the proxy, for example:

```text
EARCRAWLER_API_KEYS=proxy=<generated-secret>
```

Required rules:

- one backend secret per deployed environment
- do not reuse a personal or operator key as the proxy key
- store the backend secret in deployment-managed secret storage
- inject that secret into the proxy and the EarCrawler host separately
- keep EarCrawler bound to loopback so the backend secret is not a network-wide
  access token

For the IIS reference pattern:

- use one named key such as `proxy=<generated-secret>` only for IIS
- store the clear secret outside source control
- place the full `label:secret` value into the IIS server-variable rewrite rule
  shown in `scripts/ops/iis-earcrawler-front-door.web.config.example`
- keep the corresponding `EARCRAWLER_API_KEYS` value only on the EarCrawler host
- rotate the IIS-held secret and the EarCrawler machine environment in the same
  maintenance window

This keeps the current app contract intact while allowing a stronger front door
outside the process.

## Request attribution expectations

Broader deployments must preserve enough evidence to answer:

- which external principal made the request
- which proxy handled it
- which EarCrawler request id processed it
- which source IP reached the proxy

Required attribution behavior:

- the proxy must create or preserve a correlation id and log it
- the proxy must log the authenticated external principal
- the proxy must log the source IP and upstream TLS/auth outcome
- the proxy may forward its own correlation header, but operators must not
  assume EarCrawler will reuse it as `X-Request-Id`
- operators must retain both proxy logs and EarCrawler logs for the same
  retention window

EarCrawler already emits:

- `X-Request-Id`
- `X-Subject`
- structured logs with request identity and trace fields

In the front-door pattern, `X-Subject` will normally identify the proxy service
credential, not the human end user. End-user attribution therefore depends on
the proxy or gateway logs.

For the IIS reference pattern, the minimum useful attribution record is:

- authenticated Windows user or service principal from IIS logs
- source IP as seen by IIS
- IIS request correlation field or request id
- EarCrawler response `X-Request-Id`
- EarCrawler response `X-Subject`

This gives operators a deterministic join key between edge logs and app logs
even though EarCrawler generates its own request id.

## Secret rotation expectations

Rotation splits into two layers:

1. External identity secrets or certificates
   - rotate per the enterprise IdP, gateway, or PKI policy
   - examples: OIDC client secret, SAML signing material, mTLS certificates
2. EarCrawler backend shared secret
   - rotate in the EarCrawler host environment and in the proxy secret store
   - restart or reload the affected components
   - verify `/health` and a proxied authenticated request after rotation

Minimum backend rotation rule:

- rotate on every environment handoff, credential exposure event, or scheduled
  secret-rotation window

Do not treat a long-lived static proxy key as sufficient compensating control
for internet-facing deployment.

For the IIS reference pattern, rotation should be:

1. create a new EarCrawler backend key value on the host
2. update the IIS-injected `X-Api-Key` secret
3. recycle IIS or reload the site configuration
4. restart EarCrawler if its machine environment changed
5. verify a proxied authenticated `/health` call and archive the resulting
   `X-Request-Id`

## Minimum proxy controls

Any approved front door must provide all of the following:

- TLS termination with managed certificates
- authenticated caller identity before request forwarding
- coarse authorization or allowlisting at the edge
- request size and timeout limits no weaker than the app defaults
- rate limiting at the edge
- log retention for attribution and incident response
- explicit forwarding to a loopback-only EarCrawler listener

Recommended additional controls:

- mTLS between the proxy tier and upstream callers where feasible
- WAF or equivalent request filtering
- separate proxy credential per environment
- explicit deny rules for unused methods and paths

For the IIS reference pattern, also:

- bind IIS with managed TLS certificates only
- proxy only the documented supported routes
- deny direct access to `/docs` unless the operator explicitly wants it exposed
- keep ARR forwarding target fixed to `127.0.0.1:9001`
- capture IIS logs in the same retention and incident-response workflow as the
  EarCrawler service logs

## When the current shared-secret model is no longer sufficient

Do not rely on the current app-only static secret model once any of the
following are true:

- the API is reachable from outside the local host
- multiple human users need distinct identity or authorization decisions
- partner, vendor, or cross-network access is introduced
- audit requirements demand per-user attribution inside the request path
- security policy requires short-lived credentials, federated identity, or
  immediate revocation

At that point, the minimum acceptable posture is the reverse-proxy or gateway
pattern in this document. If per-user authorization or end-user identity must
be enforced by the EarCrawler application itself, that is new product scope and
requires a separate implementation and review.

## Exact unsupported line

Direct app exposure is no longer acceptable the moment the EarCrawler listener
is reachable from anything broader than the local host boundary.

In practical terms, direct exposure with only `EARCRAWLER_API_KEYS` is
unsupported if any of the following are true:

- Uvicorn or the EarCrawler service binds to anything other than
  `127.0.0.1` or `localhost`
- a firewall rule, port proxy, load balancer, VPN, or routed subnet can reach
  the EarCrawler listener directly
- the deployment needs per-user identity, enterprise SSO, or edge policy
  enforcement

At that line, IIS plus ARR plus external identity is the minimum approved
pattern for this Windows-first repo.

## Operator checklist

- Keep EarCrawler bound to `127.0.0.1` or equivalent local-only interface.
- Configure the reverse proxy or gateway as the only network-exposed listener.
- Authenticate callers at the proxy with enterprise identity controls.
- Configure one deployment-owned backend `X-Api-Key` credential for EarCrawler.
- Capture proxy principal, source IP, and correlation id in edge logs.
- Preserve EarCrawler `X-Request-Id` and correlate it with proxy logs.
- Rotate both proxy-tier identity secrets and the backend EarCrawler secret.
- Do not claim end-user identity enforcement inside EarCrawler unless the app
  is explicitly changed to support it.
