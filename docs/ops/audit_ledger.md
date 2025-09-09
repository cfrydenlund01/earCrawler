# Audit Ledger

Commands executed via `earctl` are recorded in a tamper‑evident JSONL ledger.
Each entry contains a rolling SHA256 hash linking it to the previous event and
optionally an HMAC if the secret `EARCTL_AUDIT_HMAC_KEY` is present in the
Windows Credential Manager.

Logs rotate daily and are stored under:

```
%PROGRAMDATA%\EarCrawler\audit
```

Verify integrity:

```bash
$ earctl audit verify
```

Force rotation:

```bash
$ earctl audit rotate
```

Old logs participate in garbage collection via `earctl gc --target audit` and
are kept for 30 days by default.
