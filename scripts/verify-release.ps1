param(
    [string]$ManifestPath = "kg/canonical/manifest.json",
    [string]$BaseDir = ".",
    [string]$ChecksumsPath = "dist/checksums.sha256",
    [string]$EvidenceOutPath = "dist/release_validation_evidence.json",
    [switch]$SkipDistChecks,
    [switch]$SkipAuthenticode,
    [switch]$RequireSignedExecutables
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-CmsSignature {
    param(
        [Parameter(Mandatory = $true)][string]$SignaturePath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path $SignaturePath)) {
        return $false
    }
    try {
        $sig = [IO.File]::ReadAllBytes($SignaturePath)
        $cms = New-Object System.Security.Cryptography.Pkcs.SignedCms
        $cms.Decode($sig)
        $cms.CheckSignature($true)
        Write-Host "$Label signature verified."
        return $true
    }
    catch {
        throw "$Label signature verification failed."
    }
}

function Parse-Checksums {
    param([Parameter(Mandatory = $true)][string]$Path)

    return Get-Content $Path | Where-Object { $_.Trim() } | ForEach-Object {
        if ($_ -notmatch "^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$") {
            throw "Malformed checksum line in ${Path}: $_"
        }
        [ordered]@{
            sha256 = $Matches[1].ToLowerInvariant()
            path = $Matches[2]
        }
    }
}

Write-Host "Support contract: one Windows host and one EarCrawler API service instance."

$manifestResolved = (Resolve-Path $ManifestPath).Path
$baseResolved = (Resolve-Path $BaseDir).Path

$manifest = Get-Content $manifestResolved -Raw | ConvertFrom-Json
$manifestCount = 0

foreach ($f in $manifest.files) {
    $path = Join-Path $baseResolved $f.path
    if (-not (Test-Path $path)) {
        throw "Missing canonical file: $($f.path)"
    }
    $hash = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $f.sha256.ToLowerInvariant()) {
        throw "Canonical hash mismatch for $($f.path)"
    }
    $manifestCount += 1
}

$manifestSignatureVerified = Test-CmsSignature -SignaturePath "$manifestResolved.sig" -Label "Canonical manifest"

$distChecked = 0
$distSignatureVerified = $false
$distSkippedReason = ""

if ($SkipDistChecks) {
    $distSkippedReason = "dist checks explicitly skipped"
}
elseif (-not (Test-Path $ChecksumsPath)) {
    $distSkippedReason = "checksums file not found"
}
else {
    $checksumsResolved = (Resolve-Path $ChecksumsPath).Path
    $checksumsDir = Split-Path -Parent $checksumsResolved
    $entries = Parse-Checksums -Path $checksumsResolved
    foreach ($entry in $entries) {
        $candidate = Join-Path $checksumsDir $entry.path
        if (-not (Test-Path $candidate)) {
            throw "Missing dist artifact listed in checksums: $($entry.path)"
        }
        $actual = (Get-FileHash $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $entry.sha256) {
            throw "Dist checksum mismatch for $($entry.path)"
        }
        $distChecked += 1
    }
    $distSignatureVerified = Test-CmsSignature -SignaturePath "$checksumsResolved.sig" -Label "Release checksums"
}

$authenticode = @()
if (-not $SkipAuthenticode) {
    $candidateDir = if (Test-Path $ChecksumsPath) { Split-Path -Parent (Resolve-Path $ChecksumsPath).Path } else { "dist" }
    if (Test-Path $candidateDir) {
        Get-ChildItem -Path $candidateDir -File -Filter *.exe -ErrorAction SilentlyContinue |
            Sort-Object Name |
            ForEach-Object {
                $sig = Get-AuthenticodeSignature -FilePath $_.FullName
                $status = $sig.Status.ToString()
                $authenticode += [ordered]@{
                    file = $_.Name
                    status = $status
                    signer = if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { "" }
                }
                if ($RequireSignedExecutables -and $status -ne "Valid") {
                    throw "Executable is not validly signed: $($_.Name) ($status)"
                }
            }
    }
}

$evidence = [ordered]@{
    schema_version = "release-validation-evidence.v1"
    generated_utc = (Get-Date).ToUniversalTime().ToString("o")
    single_host_contract = "one_windows_host_one_service_instance"
    canonical_manifest = [ordered]@{
        path = $manifestResolved
        files_verified = $manifestCount
        signature_verified = $manifestSignatureVerified
    }
    dist_artifacts = [ordered]@{
        checksums_path = $ChecksumsPath
        files_verified = $distChecked
        signature_verified = $distSignatureVerified
        skipped_reason = $distSkippedReason
    }
    authenticode = [ordered]@{
        required = $RequireSignedExecutables.IsPresent
        files = $authenticode
    }
}

$evidenceDir = Split-Path -Parent $EvidenceOutPath
if ($evidenceDir) {
    New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
}
$evidence | ConvertTo-Json -Depth 8 | Set-Content -Path $EvidenceOutPath -Encoding utf8

Write-Host "Release validation evidence written: $EvidenceOutPath"
Write-Host "All requested release checks passed."
