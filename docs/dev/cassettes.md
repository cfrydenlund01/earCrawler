# Cassettes

API interactions are recorded using VCR.py fixtures. Recording is disabled by
default. To refresh specific cassettes set the environment variable
`ALLOW_RECORD=1` and run `scripts/refresh-cassettes.ps1` on Windows. The script
records new responses in `once` mode and immediately replays them with `none`
mode to ensure deterministic playback.

Regular CI and tests run with `VCR_RECORD_MODE=none` to guarantee offline
operation.
