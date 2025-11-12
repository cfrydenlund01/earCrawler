<#
.SYNOPSIS
    Packages API contract artifacts (OpenAPI JSON + Postman collection + release notes) for external distribution.

.DESCRIPTION
    Creates a staging directory under dist/ using the current project version (unless overridden),
    copies docs/api/openapi.json and docs/api/postman_collection.json, adds release notes, and
    compresses the directory into a zip archive ready to upload alongside installers/wheels.

.PARAMETER Version
    Semantic version label for the archive. Defaults to the version in pyproject.toml.

.PARAMETER ReleaseNotesPath
    Optional path to an existing release notes file. When omitted, the script extracts the
    relevant section from CHANGELOG.md and saves it as release-notes.md inside the archive.

.EXAMPLE
    pwsh scripts/api/package_contract.ps1

.EXAMPLE
    pwsh scripts/api/package_contract.ps1 -Version 0.3.0 -ReleaseNotesPath docs/release_notes/api.md
#>
[CmdletBinding()]
param(
    [string]$Version,
    [string]$ReleaseNotesPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectVersion {
    $cmd = @"
from __future__ import annotations
import tomllib
from pathlib import Path
data = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
print(data['project']['version'])
"@
    $py = Get-Command -Name py -ErrorAction Stop
    $version = & $py.Source -c $cmd
    return $version.Trim()
}

function Get-ReleaseNotesFromChangelog {
    param([string]$TargetVersion)
    $cmd = @"
from __future__ import annotations
from pathlib import Path
import sys
version = sys.argv[1]
lines = Path('CHANGELOG.md').read_text(encoding='utf-8').splitlines()
start = None
for idx, line in enumerate(lines):
    if line.strip() == f"## [{version}]":
        start = idx + 1
        break
if start is None:
    raise SystemExit(f'No changelog section for {version}')
chunk = []
for line in lines[start:]:
    if line.startswith('## [') and not line.startswith(f'## [{version}]'):
        break
    chunk.append(line)
body = '\n'.join(chunk).strip()
print(f"# EarCrawler {version} Release Notes\n")
print(body)
"@
    $py = Get-Command -Name py -ErrorAction Stop
    $notes = & $py.Source -c $cmd $TargetVersion
    return $notes
}

if (-not $Version) {
    $Version = Get-ProjectVersion
}

$openApiPath = "docs/api/openapi.json"
$postmanPath = "docs/api/postman_collection.json"
foreach ($path in @($openApiPath, $postmanPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required artifact '$path' is missing. Run scripts/api/export_contract.py first."
    }
}

$stageDir = Join-Path "dist" ("api-contract-" + $Version)
if (Test-Path -LiteralPath $stageDir) {
    Remove-Item -LiteralPath $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

Copy-Item -LiteralPath $openApiPath -Destination (Join-Path $stageDir "openapi.json") -Force
Copy-Item -LiteralPath $postmanPath -Destination (Join-Path $stageDir "postman_collection.json") -Force

$notesDest = Join-Path $stageDir "release-notes.md"
if ($ReleaseNotesPath) {
    Copy-Item -LiteralPath $ReleaseNotesPath -Destination $notesDest -Force
} else {
    $notesContent = Get-ReleaseNotesFromChangelog -TargetVersion $Version
    Set-Content -LiteralPath $notesDest -Value $notesContent -Encoding UTF8
}

$zipPath = Join-Path "dist" ("api-contract-" + $Version + ".zip")
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath

Write-Host "Packaged API contract artifacts:"
Write-Host " - $stageDir"
Write-Host " - $zipPath"
