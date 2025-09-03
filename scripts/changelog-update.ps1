param(
    [string]$NextVersion
)

$lastTag = (git describe --tags --abbrev=0)
$commits = git log "$lastTag..HEAD" --format="%s"
$added = @()
$fixed = @()
foreach ($c in $commits) {
    if ($c -like 'feat*') { $added += ($c -replace 'feat[^:]*:','').Trim() }
    elseif ($c -like 'fix*') { $fixed += ($c -replace 'fix[^:]*:','').Trim() }
}

$section = "## [$NextVersion]`n"
if ($added.Count -gt 0) {
    $section += "### Added`n"
    foreach ($a in $added) { $section += "- $a`n" }
}
if ($fixed.Count -gt 0) {
    $section += "### Fixed`n"
    foreach ($f in $fixed) { $section += "- $f`n" }
}
$section += "`n"

$changelog = Get-Content CHANGELOG.md -Raw
Set-Content CHANGELOG.md ($section + $changelog) -Encoding utf8
Set-Content release_notes.md $section -Encoding utf8
New-Item -ItemType Directory -Force -Path 'kg/canonical' | Out-Null
Set-Content 'kg/canonical/release_notes.md' $section -Encoding utf8
