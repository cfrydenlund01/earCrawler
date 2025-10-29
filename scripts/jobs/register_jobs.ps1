SCHTASKS /Create /TN "EARAI_TradeGovJob" /TR "pwsh -NoProfile -File `"$Env:REPO_ROOT\scripts\jobs\run_tradegov_ingest.ps1`"" /SC DAILY /ST 02:00 /RU "SYSTEM" /RL LIMITED

SCHTASKS /Create /TN "EARAI_FederalRegisterJob" /TR "pwsh -NoProfile -File `"$Env:REPO_ROOT\scripts\jobs\run_federalregister_anchor.ps1`"" /SC DAILY /ST 03:00 /RU "SYSTEM" /RL LIMITED
