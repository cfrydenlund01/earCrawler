function Find-BundleExecutable {
    param(
        [Parameter(Mandatory = $true)][string[]]$Names
    )

    foreach ($name in $Names) {
        if ([string]::IsNullOrWhiteSpace($name)) {
            continue
        }
        $info = Get-Command $name -ErrorAction SilentlyContinue
        if ($info) {
            return $info.Source
        }
        try {
            $output = & where.exe $name 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) {
                $first = ($output -split "`r?`n" | Where-Object { $_ })[0]
                if ($first) {
                    return $first.Trim()
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Resolve-BundleInterpreter {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][ref]$Arguments
    )

    $cmd = $Command
    $args = @($Arguments.Value)
    if ($args.Count -eq 1 -and $args[0] -eq $null) {
        $args = @()
    }

    $normalized = [string]::IsNullOrWhiteSpace($cmd) ? '' : ([IO.Path]::GetFileName($cmd)).ToLowerInvariant()
    if ($normalized -in @('python3', 'python3.exe')) {
        $resolved = Find-BundleExecutable @('python3', 'python3.exe', 'python', 'python.exe')
        if (-not $resolved) {
            $pyResolved = Find-BundleExecutable @('py', 'py.exe')
            if ($pyResolved) {
                $resolved = $pyResolved
                $args = @('-3') + $args
            }
        }
        if (-not $resolved) {
            $candidatePaths = @()
            if ($env:VIRTUAL_ENV) {
                $candidatePaths += Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
                $candidatePaths += Join-Path $env:VIRTUAL_ENV 'Scripts/python3.exe'
                $candidatePaths += Join-Path $env:VIRTUAL_ENV 'bin/python3'
                $candidatePaths += Join-Path $env:VIRTUAL_ENV 'bin/python'
            }
            if ($env:PYTHON_HOME) {
                $candidatePaths += Join-Path $env:PYTHON_HOME 'python.exe'
                $candidatePaths += Join-Path $env:PYTHON_HOME 'bin/python3'
            }
            foreach ($candidatePath in $candidatePaths) {
                if ($candidatePath -and (Test-Path $candidatePath)) {
                    $resolved = $candidatePath
                    break
                }
            }
        }
        if ($resolved) {
            $Arguments.Value = $args
            return $resolved
        }
    }

    if ($cmd -and (Test-Path $cmd)) {
        $Arguments.Value = $args
        return $cmd
    }

    $fallback = Find-BundleExecutable @($cmd)
    if ($fallback) {
        $Arguments.Value = $args
        return $fallback
    }

    return $null
}

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

    $resolvedCmd = Resolve-BundleInterpreter -Command $cmd -Arguments ([ref]$cmdArgs)
    if (-not $resolvedCmd) {
        throw "Interpreter '$cmd' not found for executable '$Executable'"
    }

    $mergedArgs = @()
    if ($cmdArgs) { $mergedArgs += $cmdArgs }
    $mergedArgs += $resolvedExecutable
    if ($argumentList) { $mergedArgs += $argumentList }

    $cmdFileName = [IO.Path]::GetFileName($resolvedCmd).ToLowerInvariant()
    if ($cmdFileName -in @('py', 'py.exe')) {
        $scriptIndex = $cmdArgs.Count
        if ($mergedArgs.Count -gt $scriptIndex) {
            $scriptArg = [string]$mergedArgs[$scriptIndex]
            if ($scriptArg -and $scriptArg -notmatch '^".*"$') {
                $mergedArgs[$scriptIndex] = '"' + $scriptArg.Replace('"', '\"') + '"'
            }
        }
    }

    return [PSCustomObject]@{
        FilePath     = $resolvedCmd
        ArgumentList = @($mergedArgs | ForEach-Object { [string]$_ })
    }
}

function Format-BundleArgumentList {
    param(
        [string[]]$Arguments = @()
    )

    if (-not $Arguments -or $Arguments.Count -eq 0) {
        return $null
    }

    $quoted = @()
    foreach ($argument in $Arguments) {
        if ($null -eq $argument) { continue }
        $stringArgument = [string]$argument
        try {
            $quoted += [System.Management.Automation.Language.CodeGeneration]::QuoteArgument($stringArgument)
        } catch {
            $escaped = $stringArgument.Replace('"', '\"')
            $quoted += '"' + $escaped + '"'
        }
    }

    if ($quoted.Count -eq 0) {
        return $null
    }

    return ($quoted -join ' ')
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
    $argumentArray = @($launch.ArgumentList)
    $argumentString = Format-BundleArgumentList -Arguments $argumentArray
    $result = [pscustomobject]@{
        FilePath           = $launch.FilePath
        WorkingDirectory   = $WorkingDirectory
        ArgumentList       = $argumentArray
        ArgumentListString = $argumentString
    }
    if (-not $WorkingDirectory) {
        $result.PSObject.Properties.Remove('WorkingDirectory') | Out-Null
    }
    return $result
}
