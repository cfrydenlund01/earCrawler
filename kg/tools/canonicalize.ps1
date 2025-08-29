param(
    [Parameter(Mandatory=$true)][string]$Input,
    [Parameter(Mandatory=$true)][string]$Output
)

$repoRoot = Resolve-Path "$PSScriptRoot/../.."
$riot = Join-Path $repoRoot 'tools/jena/bin/riot'

# Convert to N-Quads and sort for deterministic output
& $riot --formatted=NQ $Input | Sort-Object | Set-Content -Encoding UTF8 -NoNewline $Output
