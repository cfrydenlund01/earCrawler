param(
    [String[]]$Services = @("http://localhost:8000/health"),
    [String]$LogPath = "monitor.log"
)

if (-not [System.Diagnostics.EventLog]::SourceExists("EARMonitor")) {
    New-EventLog -LogName Application -Source "EARMonitor" | Out-Null
}

foreach ($url in $Services) {
    try {
        $resp = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5
        if ($resp.status -ne "ok") {
            $msg = "Health check failed for $url"
            Add-Content -Path $LogPath -Value "$(Get-Date -Format o) $msg"
            Write-EventLog -LogName Application -Source "EARMonitor" -EntryType Error -EventId 1000 -Message $msg
        }
    } catch {
        $msg = "Health check error for $url: $($_.Exception.Message)"
        Add-Content -Path $LogPath -Value "$(Get-Date -Format o) $msg"
        Write-EventLog -LogName Application -Source "EARMonitor" -EntryType Error -EventId 1001 -Message $msg
    }
}
