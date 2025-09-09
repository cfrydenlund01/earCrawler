$ErrorActionPreference = 'Stop'
$env:EARCTL_USER = 'ci_user'

$report = New-Object System.Collections.ArrayList
$report.Add((earctl policy whoami)) | Out-Null
$report.Add((earctl diagnose)) | Out-Null
try {
    earctl gc --dry-run | Out-String | Out-Null
} catch {
    $report.Add('gc denied') | Out-Null
}
$verify = earctl audit verify
$report.Add($verify) | Out-Null
New-Item -ItemType Directory -Force -Path kg/reports | Out-Null
$report | Out-File -FilePath kg/reports/access-audit.txt -Encoding utf8
