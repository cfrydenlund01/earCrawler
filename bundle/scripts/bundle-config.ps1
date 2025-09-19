function ConvertTo-BundleObject {
    param(
        [hashtable]$Map
    )

    $obj = [PSCustomObject]@{}
    foreach ($key in $Map.Keys) {
        $value = $Map[$key]
        if ($value -is [hashtable]) {
            $value = ConvertTo-BundleObject -Map $value
        }
        Add-Member -InputObject $obj -NotePropertyName $key -NotePropertyValue $value -Force | Out-Null
    }
    return $obj
}

function ConvertFrom-SimpleBundleYaml {
    param(
        [string]$Content
    )

    $lines = $Content -split "`r?`n"
    $root = [ordered]@{}
    $stack = New-Object System.Collections.Generic.List[object]
    $stack.Add([pscustomobject]@{ Indent = -1; Target = $root }) | Out-Null

    foreach ($rawLine in $lines) {
        $line = $rawLine -replace '#.*$',''
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $indent = $line.Length - $line.TrimStart().Length
        while ($stack.Count -gt 1 -and $stack[$stack.Count - 1].Indent -ge $indent) {
            $stack.RemoveAt($stack.Count - 1)
        }

        $frame = $stack[$stack.Count - 1]
        $current = $frame.Target
        $trimmed = $line.Trim()

        if ($trimmed -notmatch '^(?<key>[^:]+):(?<value>.*)$') {
            throw "Unsupported YAML syntax: $rawLine"
        }

        $key = $Matches['key'].Trim()
        $valueText = $Matches['value']
        if ([string]::IsNullOrWhiteSpace($valueText)) {
            $child = [ordered]@{}
            $current[$key] = $child
            $stack.Add([pscustomobject]@{ Indent = $indent; Target = $child }) | Out-Null
            continue
        }

        $value = Convert-SimpleBundleValue -Text $valueText.Trim()
        $current[$key] = $value
    }

    return ConvertTo-BundleObject -Map $root
}

function Convert-SimpleBundleValue {
    param(
        [string]$Text
    )

    $value = $Text.Trim()
    if ($value.Length -eq 0) {
        return ''
    }

    if ($value -eq '~' -or $value -eq 'null') {
        return $null
    }

    if ($value.StartsWith('"') -and $value.EndsWith('"')) {
        $inner = $value.Substring(1, $value.Length - 2)
        return [System.Text.RegularExpressions.Regex]::Unescape($inner)
    }

    if ($value.StartsWith("'") -and $value.EndsWith("'")) {
        $inner = $value.Substring(1, $value.Length - 2)
        return $inner -replace "''","'"
    }

    if ($value -match '^-?\d+$') {
        return [int]$value
    }

    if ($value -match '^-?\d+\.\d+$') {
        return [double]$value
    }

    if ($value -match '^(true|false)$') {
        return [bool]::Parse($value)
    }

    return $value
}

function Import-BundleConfig {
    param(
        [string]$Path
    )

    $raw = Get-Content -Path $Path -Raw
    if (Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue) {
        return $raw | ConvertFrom-Yaml
    }

    return ConvertFrom-SimpleBundleYaml -Content $raw
}
