param()
$output = Join-Path -Path "dist" -ChildPath "checksums.sha256"
Get-ChildItem dist -File |
  Where-Object { $_.Name -notin @("checksums.sha256", "checksums.sha256.sig", "release_validation_evidence.json") } |
  ForEach-Object {
    $hash = Get-FileHash $_.FullName -Algorithm SHA256
    "$($hash.Hash)  $($_.Name)"
  } | Out-File -Encoding utf8 $output
