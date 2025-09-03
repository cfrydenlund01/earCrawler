param()
Get-ChildItem dist -File | ForEach-Object {
  $hash = Get-FileHash $_.FullName -Algorithm SHA256
  "$($hash.Hash)  $($_.Name)"
} | Out-File -Encoding utf8 dist/checksums.sha256
