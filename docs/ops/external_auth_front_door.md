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
- the proxy should forward the correlation id to EarCrawler as
  `X-Request-Id` when possible
- operators must retain both proxy logs and EarCrawler logs for the same
  retention window

EarCrawler already emits:

- `X-Request-Id`
- `X-Subject`
- structured logs with request identity and trace fields

In the front-door pattern, `X-Subject` will normally identify the proxy service
credential, not the human end user. End-user attribution therefore depends on
the proxy or gateway logs.

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
