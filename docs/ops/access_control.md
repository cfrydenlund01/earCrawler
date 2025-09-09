# Access Control

`earctl` enforces role based access control (RBAC) using `security/policy.yml`.
Roles:

- `admin` – full access.
- `maintainer` – build, release, reconcile and monitoring commands.
- `operator` – CI, inference and garbage collection.
- `reader` – read only diagnostics and query commands.

The policy file maps commands to minimal roles. Users can be granted roles via
`overrides` in the policy file or through bearer tokens stored in the Windows
Credential Manager.

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
