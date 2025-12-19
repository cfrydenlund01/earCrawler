param(
    [string]$Version = "dev"
)

if (-not $env:SOURCE_DATE_EPOCH) {
    $env:SOURCE_DATE_EPOCH = '946684800'
}
$zipDate = [DateTimeOffset]::FromUnixTimeSeconds([int64]$env:SOURCE_DATE_EPOCH).UtcDateTime.ToString('yyyyMMdd')

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) 'earcrawler-determinism'
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$firstZipCopy = Join-Path $tempRoot 'first.zip'
if (Test-Path $firstZipCopy) { Remove-Item $firstZipCopy -Force }

# First build
if (Test-Path 'kg/canonical') { Remove-Item -Recurse -Force 'kg/canonical' }
if (Test-Path 'dist') { Remove-Item -Recurse -Force 'dist' }
kg/scripts/canonical-freeze.ps1
scripts/make-canonical-zip.ps1 -Version $Version -Date $zipDate
$zip1 = Get-ChildItem dist -Filter '*.zip' | Select-Object -First 1
if (-not $zip1) {
    Write-Error 'No zip was produced in dist/ during first build.'
    exit 1
}
Copy-Item $zip1.FullName $firstZipCopy -Force

# Second build
if (Test-Path 'kg/canonical') { Remove-Item -Recurse -Force 'kg/canonical' }
if (Test-Path 'dist') { Remove-Item -Recurse -Force 'dist' }
kg/scripts/canonical-freeze.ps1
scripts/make-canonical-zip.ps1 -Version $Version -Date $zipDate
$zip2 = Get-ChildItem dist -Filter '*.zip' | Select-Object -First 1
if (-not $zip2) {
    Write-Error 'No zip was produced in dist/ during second build.'
    exit 1
}

$hash1 = (Get-FileHash $firstZipCopy -Algorithm SHA256).Hash
$hash2 = (Get-FileHash $zip2.FullName -Algorithm SHA256).Hash
if ($hash1 -ne $hash2) {
    $diffPath = Join-Path (Get-Item 'dist').FullName 'determinism-diff.txt'
    cmd /c "fc /b ""$firstZipCopy"" ""$($zip2.FullName)"" > ""$diffPath"""
    Write-Error 'Determinism check failed.'
    exit 1
} else {
    Write-Host 'Deterministic build confirmed.'
}
