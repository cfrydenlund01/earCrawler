param()
$output = Join-Path -Path "dist" -ChildPath "checksums.sha256"
Get-ChildItem dist -File |
  Where-Object { $_.Name -ne "checksums.sha256" } |
  ForEach-Object {
    $hash = Get-FileHash $_.FullName -Algorithm SHA256
    "$($hash.Hash)  $($_.Name)"
  } | Out-File -Encoding utf8 $output
