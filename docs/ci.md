# Continuous Integration

The workflow defined in `.github/workflows/ci.yml` runs our automated checks.

## Jobs

- **cpu** – Runs on `windows-latest`, installs `requirements-win.txt`, lints
  with Black and Flake8, executes tests excluding GPU markers, and uploads
  coverage results to Codecov.
- **gpu** – Runs on `ubuntu-latest` with `continue-on-error: true`, installs
  `requirements-gpu.txt`, caches the Hugging Face model hub, and runs tests
  marked with `gpu`.
- **release** – Builds and pushes Docker images when tags are pushed.

## Secrets

Each job exposes the following secrets as environment variables:

- `TRADEGOV_API_KEY`
- `FEDREG_API_KEY`

Define these in the repository settings under **Secrets and variables ➔ Actions**.
They are consumed by the workflow but never printed to logs.
