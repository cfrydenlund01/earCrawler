# Access Control

`earctl` enforces role based access control (RBAC) using `security/policy.yml`.
Roles:

- `admin` – full access.
- `maintainer` – build, release, reconcile and monitoring commands.
- `operator` – CI, inference and garbage collection.
- `reader` – read only diagnostics and query commands.

The policy file maps commands to minimal roles. Users can be granted roles via
`overrides` in the policy file.

`EARCTL_AUTH_TOKEN` may be supplied through the environment or Windows
Credential Manager for non-interactive runs, but in the current implementation
it only records token presence (`via_token`) in `policy whoami`. It does not
grant roles and it does not replace the resolved OS user or the explicit
test-only `EARCTL_USER` override path.

Check your identity:

```bash
$ earctl policy whoami
```

Dry‑run a command against policy:

```bash
$ earctl policy test --command "gc --dry-run"
```

For non‑interactive use a token may be stored under the secret name
`EARCTL_AUTH_TOKEN`.

Current behavior summary:

- Roles come from `security/policy.yml` for the resolved user identity.
- `EARCTL_USER` and `EARCTL_POLICY_PATH` are honored only when
  `EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES=1`.
- `EARCTL_AUTH_TOKEN` only toggles `via_token` in `policy whoami`; it is not a
  token-to-role mapping mechanism.
