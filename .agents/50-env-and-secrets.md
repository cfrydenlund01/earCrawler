# Env & Secrets

## Rules
- Never print secret values (API keys, tokens, credential exports, `.env`, etc.).
- If secret-like material is discovered in versioned files: propose remediation without exposing values (remove from git, add to `.gitignore`, provide `.env.example`, recommend key rotation).

## Common repo patterns
- `.env` is gitignored; `.env.example` is the template.
- Local LLM secrets live in `config/llm_secrets.env` (gitignored).
- CI injects API keys via secrets (see `.github/workflows/ci.yml`).

## Where credentials come from
- Clients support environment variables and/or OS credential stores (Windows Credential Manager/keyring workflows are documented in `README.md` and `RUNBOOK.md`).

