# Placeholder script for Windows service smoke checks. No-op in CI.
Write-Host "Run on Windows hosts to inspect the EarCrawler-API service state:" \
    "`n  Get-Service EarCrawler-API" \
    "`n  Get-WinEvent -LogName Application -MaxEvents 20 | Where-Object { $_.Message -like '*EarCrawler-API*' }"
