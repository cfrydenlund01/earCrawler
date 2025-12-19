param(
    [string]$CanonicalDir = "kg/canonical",
    [string]$DistDir = "dist"
)

New-Item -ItemType Directory -Force -Path $CanonicalDir | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$manifestPath = Join-Path $CanonicalDir 'manifest.json'
$checksumsPath = Join-Path $CanonicalDir 'checksums.sha256'
if (Test-Path $manifestPath) { Remove-Item $manifestPath }
if (Test-Path $checksumsPath) { Remove-Item $checksumsPath }
$files = @()

Get-ChildItem -Path $CanonicalDir -Recurse | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName | ForEach-Object {
    $rel = [IO.Path]::GetRelativePath((Get-Item '.').FullName, $_.FullName).Replace('\\','/')
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $files += [ordered]@{ path = $rel; size = $_.Length; sha256 = $hash }
}

if ($DistDir -and (Test-Path $DistDir)) {
    Get-ChildItem -Path $DistDir -Filter *.zip | Sort-Object FullName | ForEach-Object {
        $rel = [IO.Path]::GetRelativePath((Get-Item '.').FullName, $_.FullName).Replace('\\','/')
        $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
        $files += [ordered]@{ path = $rel; size = $_.Length; sha256 = $hash }
    }
}

$manifest = [ordered]@{ files = $files }
$payload = $manifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($manifestPath, $payload, $utf8NoBom)
$checksums = $files | ForEach-Object { "$($_.sha256) *$($_.path)" }
[IO.File]::WriteAllLines($checksumsPath, $checksums, $utf8NoBom)
