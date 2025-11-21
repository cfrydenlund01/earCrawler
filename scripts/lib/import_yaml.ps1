Set-StrictMode -Version Latest

function Resolve-YamlPython {
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return @{ Path = $env:EARCTL_PYTHON; Args = @() }
    }

    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return @{ Path = $cmd.Source; Args = @() }
        }
    }

    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher) {
        return @{ Path = $launcher.Source; Args = @('-3') }
    }

    return $null
}

function Import-YamlDocument {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "YAML file not found at $Path"
    }

    $raw = Get-Content -Path $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }

    if (Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue) {
        return $raw | ConvertFrom-Yaml
    }

    $pythonInfo = Resolve-YamlPython
    if (-not $pythonInfo) {
        throw "ConvertFrom-Yaml is unavailable and Python could not be located to parse $Path."
    }

    $script = @"
import json, pathlib, sys
try:
    import yaml
except ImportError as exc:
    sys.stderr.write(f"PyYAML missing: {exc}\n")
    sys.exit(2)
path = pathlib.Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding='utf-8'))
json.dump(data, sys.stdout)
"@

    $tempFile = [System.IO.Path]::GetTempFileName() + '.py'
    Set-Content -Path $tempFile -Value $script -Encoding UTF8
    try {
        $args = @()
        if ($pythonInfo.Args) { $args += $pythonInfo.Args }
        $args += @($tempFile, $Path)
        $json = & $pythonInfo.Path @args
        if ($LASTEXITCODE -ne 0) {
            throw "Python exited with code $LASTEXITCODE while parsing $Path"
        }
        return $json | ConvertFrom-Json -Depth 64
    }
    finally {
        Remove-Item $tempFile -ErrorAction SilentlyContinue
    }
}
