# Check Java
$java = Get-Command java -ErrorAction SilentlyContinue
if (-not $java) {
  Write-Output "Java: WARN not found on PATH"
} else {
  $ver = & java -version 2>&1
  $is64 = $ver -match "64-Bit"
  if ($ver -match '"(\d+)' ) { $major = [int]$matches[1] } else { $major = 0 }
  if ($major -ge 11 -and $is64) {
    Write-Output "Java: OK"
  } else {
    Write-Output "Java: WARN $ver"
  }
}

# Check Jena bat folder in PATH
$pathItems = $env:PATH -split ';'
$jena = $pathItems | Where-Object { $_ -match '\\bat(\\)?$' }
if ($jena) {
  Write-Output "Jena bat\\ folder: OK"
} else {
  Write-Output "Jena bat\\ folder: WARN"
}

# Check git longpaths
$longpaths = git config --get core.longpaths 2>$null
if ($longpaths -eq 'true') {
  Write-Output "git core.longpaths=true: OK"
} else {
  Write-Output "git core.longpaths=true: WARN"
}

exit 0
