function Resolve-BundleCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $null
    )

    $argumentList = @()
    if ($Arguments) {
        $argumentList = @($Arguments | ForEach-Object { [string]$_ })
    }

    if (-not $IsWindows) {
        return [PSCustomObject]@{
            FilePath     = $Executable
            ArgumentList = $argumentList
        }
    }

    $extension = [System.IO.Path]::GetExtension($Executable)
    if ($extension) {
        $normalized = $extension.ToLowerInvariant()
        if (@('.exe', '.com', '.bat', '.cmd') -contains $normalized) {
            return [PSCustomObject]@{
                FilePath     = $Executable
                ArgumentList = $argumentList
            }
        }
    }

    $resolvedExecutable = $Executable
    if (-not (Test-Path $resolvedExecutable)) {
        if ($WorkingDirectory) {
            $candidate = Join-Path $WorkingDirectory $Executable
            if (Test-Path $candidate) {
                $resolvedExecutable = (Resolve-Path $candidate).Path
            }
        }
    } else {
        $resolvedExecutable = (Resolve-Path $resolvedExecutable).Path
    }

    if (-not (Test-Path $resolvedExecutable)) {
        return [PSCustomObject]@{
            FilePath     = $Executable
            ArgumentList = $argumentList
        }
    }

    $shebangLine = $null
    try {
        $shebangLine = Get-Content -Path $resolvedExecutable -TotalCount 1 -ErrorAction Stop
    } catch {
        $shebangLine = $null
    }

    if (-not $shebangLine -or $shebangLine -notmatch '^#!\s*(.+)$') {
        return [PSCustomObject]@{
            FilePath     = $Executable
            ArgumentList = $argumentList
        }
    }

    $commandLine = $Matches[1].Trim()
    if (-not $commandLine) {
        return [PSCustomObject]@{
            FilePath     = $Executable
            ArgumentList = $argumentList
        }
    }

    $tokens = @()
    $buffer = ''
    $inQuotes = $false
    for ($i = 0; $i -lt $commandLine.Length; $i++) {
        $char = $commandLine[$i]
        if ($char -eq '"') {
            $inQuotes = -not $inQuotes
            continue
        }
        if (-not $inQuotes -and [char]::IsWhiteSpace($char)) {
            if ($buffer.Length -gt 0) {
                $tokens += $buffer
                $buffer = ''
            }
            continue
        }
        $buffer += $char
    }
    if ($buffer.Length -gt 0) {
        $tokens += $buffer
    }

    if (-not $tokens -or $tokens.Count -eq 0) {
        return [PSCustomObject]@{
            FilePath     = $Executable
            ArgumentList = $argumentList
        }
    }

    $cmd = $tokens[0]
    $cmdArgs = @()
    if ($tokens.Count -gt 1) {
        $cmdArgs = $tokens[1..($tokens.Count - 1)]
    }

    if ([System.IO.Path]::GetFileName($cmd).ToLowerInvariant() -eq 'env' -and $cmdArgs.Count -ge 1) {
        $cmd = $cmdArgs[0]
        if ($cmdArgs.Count -gt 1) {
            $cmdArgs = $cmdArgs[1..($cmdArgs.Count - 1)]
        } else {
            $cmdArgs = @()
        }
    }

    if ($cmd -eq 'python3' -and -not (Get-Command 'python3' -ErrorAction SilentlyContinue)) {
        if (Get-Command 'python' -ErrorAction SilentlyContinue) {
            $cmd = 'python'
        }
    }

    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "Interpreter '$cmd' not found for executable '$Executable'"
    }

    $mergedArgs = @()
    if ($cmdArgs) { $mergedArgs += $cmdArgs }
    $mergedArgs += $resolvedExecutable
    if ($argumentList) { $mergedArgs += $argumentList }

    return [PSCustomObject]@{
        FilePath     = $cmd
        ArgumentList = @($mergedArgs | ForEach-Object { [string]$_ })
    }
}

function Invoke-BundleProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $null
    )

    $launch = Resolve-BundleCommand -Executable $Executable -Arguments $Arguments -WorkingDirectory $WorkingDirectory
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $launch.FilePath
    $startInfo.UseShellExecute = $false
    if ($WorkingDirectory) {
        $startInfo.WorkingDirectory = $WorkingDirectory
    }
    foreach ($argument in $launch.ArgumentList) {
        [void]$startInfo.ArgumentList.Add([string]$argument)
    }

    $process = [System.Diagnostics.Process]::Start($startInfo)
    if (-not $process) {
        throw "Failed to start process '$($launch.FilePath)'"
    }
    try {
        $process.WaitForExit()
        return $process.ExitCode
    } finally {
        $process.Dispose()
    }
}

function Get-BundleProcessStartParameters {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $null
    )

    $launch = Resolve-BundleCommand -Executable $Executable -Arguments $Arguments -WorkingDirectory $WorkingDirectory
    $params = @{
        FilePath     = $launch.FilePath
        ArgumentList = $launch.ArgumentList
    }
    if ($WorkingDirectory) {
        $params.WorkingDirectory = $WorkingDirectory
    }
    return $params
}
