[CmdletBinding()]
param(
    [string]$Source = 'EarCrawler'
)

<#
    Requires administrator privileges to register a Windows Event Log source.
    On GitHub runners this may fail with access denied; the script will emit
    a warning but continue without failing the job.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

try {
    if (-not [System.Diagnostics.EventLog]::SourceExists($Source)) {
        [System.Diagnostics.EventLog]::CreateEventSource($Source, 'Application')
        Write-Host "Registered Event Log source '$Source'"
    } else {
        Write-Host "Event Log source '$Source' already exists"
    }
} catch {
    Write-Warning "Unable to register Event Log source '$Source': $($_.Exception.Message)"
}
