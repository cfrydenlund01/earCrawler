param([string]$Dir = "dist")
$cert = $Env:SIGNING_CERT_PFX_BASE64
$pwd = $Env:SIGNING_CERT_PASSWORD
$subject = $Env:SIGNING_SUBJECT
$thumb = $Env:SIGNING_THUMBPRINT
$ts = $Env:TIMESTAMP_URL
if (-not $ts) { $ts = "http://timestamp.digicert.com" }

if (-not $cert -or -not $pwd -or (-not $subject -and -not $thumb)) {
  Write-Host "sign-artifacts: signing secrets not provided; skipping"
  exit 0
}

$temp = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $temp | Out-Null
$pfx = Join-Path $temp "cert.pfx"
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($cert)) | Out-Null
certutil -f -p $pwd -importpfx $pfx | Out-Null

if ($thumb) { $certArg = "/sha1 $thumb" } else { $certArg = "/n `"$subject`"" }
Get-ChildItem $Dir -Filter *.exe | ForEach-Object {
  & signtool.exe sign /fd sha256 /tr $ts /td sha256 $certArg $_.FullName
  & signtool.exe verify /pa $_.FullName
}
Remove-Item $pfx -Force
Remove-Item $temp -Force
