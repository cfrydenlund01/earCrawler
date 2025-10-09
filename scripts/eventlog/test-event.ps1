[CmdletBinding()]
param(
    [string]$Source = 'EarCrawler',
    [ValidateSet('Information','Warning','Error')]
    [string]$Level = 'Information',
    [string]$Message = 'EarCrawler observability smoke test'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([System.Diagnostics.EventLog]::SourceExists($Source)) {
    [System.Diagnostics.EventLog]::WriteEntry($Source, $Message, [System.Diagnostics.EventLogEntryType]::$Level)
    Write-Host "Event written to '$Source'"
} else {
    Write-Warning "Event Log source '$Source' is not registered"
}
