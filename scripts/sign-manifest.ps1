param(
    [string]$ManifestPath = "kg/canonical/manifest.json"
)

$certB64 = $env:SIGNING_CERT_PFX_BASE64
if (-not $certB64) {
    Write-Host 'No signing certificate provided; skipping.'
    return
}
if (-not $env:SIGNING_CERT_PASSWORD) {
    Write-Host 'SIGNING_CERT_PASSWORD not set; skipping.'
    return
}

$bytes = [Convert]::FromBase64String($certB64)
$pfx = New-TemporaryFile
[IO.File]::WriteAllBytes($pfx, $bytes)
$pwd = ConvertTo-SecureString $env:SIGNING_CERT_PASSWORD -AsPlainText -Force
$cert = Get-PfxCertificate -FilePath $pfx -Password $pwd

$content = Get-Content -Path $ManifestPath -Encoding Byte -Raw
$cms = New-Object System.Security.Cryptography.Pkcs.ContentInfo,($content)
$signed = New-Object System.Security.Cryptography.Pkcs.SignedCms($cms,$false)
$signer = New-Object System.Security.Cryptography.Pkcs.CmsSigner($cert)
$signed.ComputeSignature($signer)
[IO.File]::WriteAllBytes("$ManifestPath.sig", $signed.Encode())

# verify
$verify = New-Object System.Security.Cryptography.Pkcs.SignedCms
$verify.Decode([IO.File]::ReadAllBytes("$ManifestPath.sig"))
try {
    $verify.CheckSignature($true)
    Write-Host 'Signature verified.'
} catch {
    Write-Error 'Signature verification failed.'
    exit 1
}
