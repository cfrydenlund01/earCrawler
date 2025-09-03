$ErrorActionPreference = 'Stop'
$taskName = 'EarCrawler-GC'
$action = New-ScheduledTaskAction -Execute 'earctl' -Argument 'gc --apply --target all --yes'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Force | Out-Null
} else {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description 'EarCrawler GC' | Out-Null
}
Write-Output "Scheduled $taskName"
