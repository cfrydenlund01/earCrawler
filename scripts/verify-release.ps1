param(
    [string]$ManifestPath = "kg/canonical/manifest.json",
    [string]$BaseDir = "."
)

$manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
foreach ($f in $manifest.files) {
    $path = Join-Path $BaseDir $f.path
    if (-not (Test-Path $path)) {
        Write-Error "Missing file $($f.path)"
        exit 1
    }
    $hash = (Get-FileHash $path -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $f.sha256.ToLower()) {
        Write-Error "Hash mismatch for $($f.path)"
        exit 1
    }
}
if (Test-Path "$ManifestPath.sig") {
    $content = Get-Content -Path $ManifestPath -Encoding Byte -Raw
    $sig = [IO.File]::ReadAllBytes("$ManifestPath.sig")
    $cms = New-Object System.Security.Cryptography.Pkcs.SignedCms
    $cms.Decode($sig)
    try {
        $cms.CheckSignature($true)
    } catch {
        Write-Error 'Signature verification failed.'
        exit 1
    }
}
Write-Host 'All files verified.'
