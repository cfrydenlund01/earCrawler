$repoRoot = Resolve-Path "$PSScriptRoot/.."
$versions = Get-Content (Join-Path $repoRoot 'tools/versions.json') | ConvertFrom-Json
$cache = Join-Path $repoRoot '.cache/java'
New-Item -ItemType Directory -Force -Path $cache | Out-Null

function Verify-Tool($name, $base) {
    $info = $versions.$name
    $ver = $info.version
    $expected = $info.sha512.ToLower()
    $zip = Join-Path $cache "$name-$ver.zip"
    $url = "$base-$ver.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip
    $shaRef = (Invoke-WebRequest -Uri "$url.sha512").Content.Split()[0].ToLower()
    $actual = (Get-FileHash $zip -Algorithm SHA512).Hash.ToLower()
    if ($actual -ne $expected -or $actual -ne $shaRef) {
        throw "SHA512 mismatch for $name: expected $expected, ref $shaRef, got $actual"
    }
}

Verify-Tool 'jena' 'https://archive.apache.org/dist/jena/binaries/apache-jena'
Verify-Tool 'fuseki' 'https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki'
