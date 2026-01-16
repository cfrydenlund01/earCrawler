# Testing & Quality

## Standard commands (mirrors CI)
- Format check: `black --check .`
- Lint: `flake8 .`
- Tests: `pytest -q --disable-warnings --maxfail=1`

## Pytest markers
See `pytest.ini`:
- Default excludes network tests via `-m "not network"`.
- GPU tests are marked `gpu` (CI runs them conditionally).

## Suggested order
1) Run the smallest relevant test subset (single file/dir) for changes.
2) Run the standard CI commands above before finalizing.

