param(
    [string]$SourceDir = "kg/canonical",
    [string]$OutputDir = "dist",
    [string]$Version = "dev",
    [string]$Date = (Get-Date -Format 'yyyyMMdd')
)

Add-Type -AssemblyName System.IO.Compression.FileSystem

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$zipName = "earcrawler-kg-$Version-$Date-snapshot.zip"
$zipPath = Join-Path $OutputDir $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath }

if ($env:SOURCE_DATE_EPOCH) {
    $epoch = [int64]$env:SOURCE_DATE_EPOCH
    $fixedTime = [DateTimeOffset]::FromUnixTimeSeconds($epoch)
} else {
    $fixedTime = [DateTimeOffset]::new(2000,1,1,0,0,0,[TimeSpan]::Zero)
}

$files = Get-ChildItem -Path $SourceDir -Recurse | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
foreach ($f in $files) {
    $relative = [IO.Path]::GetRelativePath($SourceDir, $f.FullName).Replace('\','/')
    $entry = $zip.CreateEntryFromFile($f.FullName, $relative)
    $entry.LastWriteTime = $fixedTime
}
$zip.Dispose()
