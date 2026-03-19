param(
    [string]$ManifestPath = "kg/canonical/manifest.json",
    [string]$BaseDir = ".",
    [string]$ChecksumsPath = "dist/checksums.sha256",
    [string]$EvidenceOutPath = "dist/release_validation_evidence.json",
    [string]$ApiSmokeReportPath = "dist/api_smoke.json",
    [string]$OptionalRuntimeSmokeReportPath = "dist/optional_runtime_smoke.json",
    [string]$InstalledRuntimeSmokeReportPath = "dist/installed_runtime_smoke.json",
    [switch]$SkipDistChecks,
    [switch]$SkipAuthenticode,
    [switch]$RequireSignedExecutables,
    [switch]$RequireCompleteEvidence
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

function Get-PlaceholderArtifacts {
    param([string[]]$Roots)

    $matches = @()
    foreach ($root in $Roots) {
        if (-not $root) {
            continue
        }
        if (-not (Test-Path $root)) {
            continue
        }
        Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "PLACEHOLDER" } |
            ForEach-Object {
                $matches += $_.FullName
            }
    }
    return $matches
}

function Read-JsonReport {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path $Path)) {
        return $null
    }
    try {
        return Get-Content $Path -Raw | ConvertFrom-Json
    }
    catch {
        throw "$Label report is not valid JSON: $Path"
    }
}

function Test-SupportedApiSmokeReport {
    param([Parameter(Mandatory = $true)][string]$Path)

    $payload = Read-JsonReport -Path $Path -Label "Supported API smoke"
    if ($null -eq $payload) {
        return [ordered]@{
            path = $Path
            present = $false
            status = "missing"
            overall_status = ""
        }
    }

    $expectedChecks = @("health", "entity", "lineage", "sparql")
    $checks = @{}
    foreach ($check in @($payload.checks)) {
        $checks[[string]$check.name] = $check
    }
    $missingChecks = @($expectedChecks | Where-Object { -not $checks.ContainsKey($_) })
    $failedChecks = @(
        $expectedChecks | Where-Object {
            $checks.ContainsKey($_) -and (
                [string]$checks[$_].status -ne "passed" -or
                [int]$checks[$_].status_code -ne 200
            )
        }
    )
    $reportStatus = if (
        [string]$payload.schema_version -eq "supported-api-smoke.v1" -and
        [string]$payload.overall_status -eq "passed" -and
        $missingChecks.Count -eq 0 -and
        $failedChecks.Count -eq 0
    ) {
        "passed"
    }
    else {
        "failed"
    }

    return [ordered]@{
        path = $Path
        present = $true
        schema_version = [string]$payload.schema_version
        overall_status = [string]$payload.overall_status
        missing_checks = $missingChecks
        failed_checks = $failedChecks
        status = $reportStatus
    }
}

function Test-OptionalRuntimeSmokeReport {
    param([Parameter(Mandatory = $true)][string]$Path)

    $payload = Read-JsonReport -Path $Path -Label "Optional runtime smoke"
    if ($null -eq $payload) {
        return [ordered]@{
            path = $Path
            present = $false
            status = "missing"
            overall_status = ""
        }
    }

    $reportStatus = if (
        [string]$payload.schema_version -eq "optional-runtime-smoke.v1" -and
        [string]$payload.overall_status -eq "passed"
    ) {
        "passed"
    }
    else {
        "failed"
    }

    return [ordered]@{
        path = $Path
        present = $true
        schema_version = [string]$payload.schema_version
        overall_status = [string]$payload.overall_status
        status = $reportStatus
    }
}

function Test-InstalledRuntimeSmokeReport {
    param([Parameter(Mandatory = $true)][string]$Path)

    $payload = Read-JsonReport -Path $Path -Label "Installed runtime smoke"
    if ($null -eq $payload) {
        return [ordered]@{
            path = $Path
            present = $false
            status = "missing"
            overall_status = ""
            missing_checks = @()
            failed_checks = @()
        }
    }

    $expectedChecks = @(
        "health_http_200",
        "supported_api_smoke",
        "runtime_contract_topology",
        "runtime_contract_declared_instance_count",
        "runtime_contract_capability_registry_schema",
        "runtime_contract_api_default_surface",
        "runtime_contract_api_search",
        "runtime_contract_kg_expansion"
    )
    $checks = @{}
    foreach ($check in @($payload.checks)) {
        $checks[[string]$check.name] = $check
    }
    $missingChecks = @($expectedChecks | Where-Object { -not $checks.ContainsKey($_) })
    $failedChecks = @(
        $expectedChecks | Where-Object {
            $checks.ContainsKey($_) -and [bool]$checks[$_].passed -ne $true
        }
    )

    $reportStatus = if (
        [string]$payload.schema_version -eq "installed-runtime-smoke.v1" -and
        [string]$payload.overall_status -eq "passed" -and
        $missingChecks.Count -eq 0 -and
        $failedChecks.Count -eq 0
    ) {
        "passed"
    }
    else {
        "failed"
    }

    return [ordered]@{
        path = $Path
        present = $true
        schema_version = [string]$payload.schema_version
        overall_status = [string]$payload.overall_status
        missing_checks = $missingChecks
        failed_checks = $failedChecks
        status = $reportStatus
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
$supportedApiSmoke = Test-SupportedApiSmokeReport -Path $ApiSmokeReportPath
$optionalRuntimeSmoke = Test-OptionalRuntimeSmokeReport -Path $OptionalRuntimeSmokeReportPath
$installedRuntimeSmoke = Test-InstalledRuntimeSmokeReport -Path $InstalledRuntimeSmokeReportPath

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

    $placeholderRoots = @($checksumsDir)
    if ((Split-Path -Leaf $checksumsDir).ToLowerInvariant() -eq "dist") {
        $offlineBundleDir = Join-Path $checksumsDir "offline_bundle"
        if (Test-Path $offlineBundleDir) {
            $placeholderRoots += $offlineBundleDir
        }
    }
    $placeholderArtifacts = @(Get-PlaceholderArtifacts -Roots $placeholderRoots)
    if ($placeholderArtifacts.Count -gt 0) {
        $placeholderList = ($placeholderArtifacts | Sort-Object | ForEach-Object { " - $_" }) -join [Environment]::NewLine
        throw "Placeholder artifacts are not allowed in distributable outputs:`n$placeholderList"
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

$evidenceFailures = @()
if ($RequireCompleteEvidence) {
    if (-not $manifestSignatureVerified) {
        $evidenceFailures += "Canonical manifest signature verification is required."
    }
    if ($distSkippedReason) {
        $evidenceFailures += "Dist artifact verification was skipped or incomplete: $distSkippedReason."
    }
    if ($distChecked -lt 1) {
        $evidenceFailures += "At least one distributable artifact checksum must be verified."
    }
    if (-not $distSignatureVerified) {
        $evidenceFailures += "Release checksums signature verification is required."
    }
    if ($RequireSignedExecutables -and $authenticode.Count -lt 1) {
        $evidenceFailures += "At least one signed executable must be present for release publication."
    }
    if ([string]$supportedApiSmoke.status -ne "passed") {
        $evidenceFailures += "Supported API smoke parity evidence is required and must pass."
    }
    if ([string]$optionalRuntimeSmoke.status -ne "passed") {
        $evidenceFailures += "Optional runtime smoke evidence is required and must pass."
    }
    if ([string]$installedRuntimeSmoke.status -ne "passed") {
        $evidenceFailures += "Installed runtime smoke evidence is required and must pass."
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
    supported_api_smoke = $supportedApiSmoke
    optional_runtime_smoke = $optionalRuntimeSmoke
    installed_runtime_smoke = $installedRuntimeSmoke
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

if ($evidenceFailures.Count -gt 0) {
    $failureList = ($evidenceFailures | ForEach-Object { " - $_" }) -join [Environment]::NewLine
    throw "Release evidence is incomplete:`n$failureList"
}

Write-Host "Release validation evidence written: $EvidenceOutPath"
Write-Host "All requested release checks passed."




