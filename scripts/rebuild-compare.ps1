param(
    [string]$Version = "dev"
)

$env:SOURCE_DATE_EPOCH = $env:SOURCE_DATE_EPOCH ?? '946684800'

# First build
if (Test-Path 'kg/canonical') { Remove-Item -Recurse -Force 'kg/canonical' }
if (Test-Path 'dist') { Remove-Item -Recurse -Force 'dist' }
kg/scripts/canonical-freeze.ps1
scripts/make-canonical-zip.ps1 -Version $Version
$zip1 = Get-ChildItem dist -Filter '*.zip' | Select-Object -First 1
Copy-Item $zip1.FullName 'dist/first.zip'

# Second build
if (Test-Path 'kg/canonical') { Remove-Item -Recurse -Force 'kg/canonical' }
if (Test-Path 'dist') { Remove-Item -Recurse -Force 'dist' }
kg/scripts/canonical-freeze.ps1
scripts/make-canonical-zip.ps1 -Version $Version
$zip2 = Get-ChildItem dist -Filter '*.zip' | Select-Object -First 1

$hash1 = (Get-FileHash 'dist/first.zip' -Algorithm SHA256).Hash
$hash2 = (Get-FileHash $zip2.FullName -Algorithm SHA256).Hash
if ($hash1 -ne $hash2) {
    fc /b 'dist/first.zip' $zip2.FullName > 'dist/determinism-diff.txt'
    Write-Error 'Determinism check failed.'
    exit 1
} else {
    Write-Host 'Deterministic build confirmed.'
}
