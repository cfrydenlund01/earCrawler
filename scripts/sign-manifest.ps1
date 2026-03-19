param(
    [Alias('ManifestPath')]
    [string]$FilePath = "kg/canonical/manifest.json",
    [string]$Thumbprint = $env:SIGNING_THUMBPRINT,
    [string]$Subject = $env:SIGNING_SUBJECT,
    [string]$PfxBase64 = $env:SIGNING_CERT_PFX_BASE64,
    [string]$PfxPassword = $env:SIGNING_CERT_PASSWORD,
    [string]$CertStoreLocation = "Cert:\CurrentUser\My"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SigningCertificate {
    param(
        [string]$ResolvedThumbprint,
        [string]$ResolvedSubject,
        [string]$ResolvedPfxBase64,
        [string]$ResolvedPfxPassword,
        [string]$StoreLocation
    )

    if ($ResolvedPfxBase64) {
        if (-not $ResolvedPfxPassword) {
            throw 'SIGNING_CERT_PASSWORD must be set when SIGNING_CERT_PFX_BASE64 is provided.'
        }
        $bytes = [Convert]::FromBase64String($ResolvedPfxBase64)
        $pwd = ConvertTo-SecureString $ResolvedPfxPassword -AsPlainText -Force
        return [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
            $bytes,
            $pwd,
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable
        )
    }

    $candidates = @(Get-ChildItem -Path $StoreLocation | Where-Object { $_.HasPrivateKey })
    if ($ResolvedThumbprint) {
        $normalizedThumbprint = ($ResolvedThumbprint -replace '\s+', '').ToUpperInvariant()
        $match = @($candidates | Where-Object { $_.Thumbprint.ToUpperInvariant() -eq $normalizedThumbprint } | Select-Object -First 1)
        if ($match.Count -lt 1) {
            throw "Signing certificate not found for thumbprint: $ResolvedThumbprint"
        }
        return $match[0]
    }
    if ($ResolvedSubject) {
        $match = @(
            $candidates |
                Where-Object { $_.Subject -eq $ResolvedSubject } |
                Sort-Object NotAfter -Descending |
                Select-Object -First 1
        )
        if ($match.Count -lt 1) {
            throw "Signing certificate not found for subject: $ResolvedSubject"
        }
        return $match[0]
    }

    return $null
}

$resolvedPath = (Resolve-Path $FilePath).Path
$cert = Get-SigningCertificate `
    -ResolvedThumbprint $Thumbprint `
    -ResolvedSubject $Subject `
    -ResolvedPfxBase64 $PfxBase64 `
    -ResolvedPfxPassword $PfxPassword `
    -StoreLocation $CertStoreLocation
if ($null -eq $cert) {
    Write-Host 'No signing certificate provided; skipping.'
    return
}

$content = [IO.File]::ReadAllBytes($resolvedPath)
$cms = New-Object System.Security.Cryptography.Pkcs.ContentInfo (, $content)
$signed = New-Object System.Security.Cryptography.Pkcs.SignedCms($cms, $false)
$signer = New-Object System.Security.Cryptography.Pkcs.CmsSigner($cert)
$signed.ComputeSignature($signer)
$signaturePath = "$resolvedPath.sig"
[IO.File]::WriteAllBytes($signaturePath, $signed.Encode())

$verify = New-Object System.Security.Cryptography.Pkcs.SignedCms
$verify.Decode([IO.File]::ReadAllBytes($signaturePath))
try {
    $verify.CheckSignature($true)
    Write-Host "Signature verified: $signaturePath"
}
catch {
    throw 'Signature verification failed.'
}
