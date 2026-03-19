param(
  [string]$Dir = "dist",
  [string]$Thumbprint = $Env:SIGNING_THUMBPRINT,
  [string]$Subject = $Env:SIGNING_SUBJECT,
  [string]$PfxBase64 = $Env:SIGNING_CERT_PFX_BASE64,
  [string]$PfxPassword = $Env:SIGNING_CERT_PASSWORD,
  [string]$TimestampUrl = $Env:TIMESTAMP_URL,
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

function Invoke-AuthenticodeSign {
  param(
    [Parameter(Mandatory = $true)]$Certificate,
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [string]$ResolvedTimestampUrl
  )

  $params = @{
    FilePath = $TargetPath
    Certificate = $Certificate
    HashAlgorithm = 'SHA256'
    Force = $true
  }
  if ($ResolvedTimestampUrl) {
    try {
      $signature = Set-AuthenticodeSignature @params -TimestampServer $ResolvedTimestampUrl
    }
    catch {
      Write-Warning "Timestamping failed for $TargetPath; retrying without timestamp."
      $signature = Set-AuthenticodeSignature @params
    }
  }
  else {
    $signature = Set-AuthenticodeSignature @params
  }

  if ($signature.Status -ne 'Valid') {
    throw "Authenticode signing failed for $TargetPath ($($signature.Status))"
  }
}

$cert = Get-SigningCertificate `
  -ResolvedThumbprint $Thumbprint `
  -ResolvedSubject $Subject `
  -ResolvedPfxBase64 $PfxBase64 `
  -ResolvedPfxPassword $PfxPassword `
  -StoreLocation $CertStoreLocation
if ($null -eq $cert) {
  Write-Host "sign-artifacts: signing certificate not provided; skipping"
  exit 0
}

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
$targets = @(Get-ChildItem $Dir -Filter *.exe -File | Sort-Object Name)
if ($targets.Count -lt 1) {
  Write-Host "sign-artifacts: no executable artifacts found"
  exit 0
}

foreach ($target in $targets) {
  if ($signtool) {
    $signArgs = @('sign', '/fd', 'sha256')
    if ($TimestampUrl) {
      $signArgs += @('/tr', $TimestampUrl, '/td', 'sha256')
    }
    if ($Thumbprint) {
      $signArgs += @('/sha1', ($Thumbprint -replace '\s+', ''))
    }
    elseif ($Subject) {
      $signArgs += @('/n', $Subject)
    }
    else {
      $signArgs += @('/sha1', $cert.Thumbprint)
    }
    $signArgs += $target.FullName
    & $signtool.Source @signArgs
    if ($LASTEXITCODE -ne 0) {
      throw "signtool signing failed for $($target.FullName)"
    }

    & $signtool.Source verify /pa $target.FullName
    if ($LASTEXITCODE -ne 0) {
      throw "signtool verification failed for $($target.FullName)"
    }
  }
  else {
    Invoke-AuthenticodeSign -Certificate $cert -TargetPath $target.FullName -ResolvedTimestampUrl $TimestampUrl
  }

  $verification = Get-AuthenticodeSignature -FilePath $target.FullName
  if ($verification.Status -ne 'Valid') {
    throw "Executable signature is not valid: $($target.Name) ($($verification.Status))"
  }
  Write-Host "Signed executable: $($target.Name)"
}
