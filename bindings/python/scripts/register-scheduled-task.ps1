#Requires -Version 5.1
<#
.SYNOPSIS
    Register a Windows Task Scheduler daily job for Aureum paper trading.
.DESCRIPTION
    Creates a scheduled task that runs ``aureum-daily-task.ps1`` every weekday
    morning before the US market open.  Run this script as Administrator.
.PARAMETER TaskName
    The Windows Task Scheduler task name.
.PARAMETER ScriptPath
    Path to ``aureum-daily-task.ps1``.
.PARAMETER RunTime
    Daily run time (HH:mm).  Default 09:35 US/Eastern runs five minutes after the
    09:30 equity market open so market-open checks pass.
.PARAMETER DaysOfWeek
    Comma-separated list of weekdays to run (default: Monday through Friday).
#>
param(
    [string]$TaskName = "AureumDailyPaperTrading",
    [string]$ScriptPath = "$PSScriptRoot\aureum-daily-task.ps1",
    [string]$RunTime = "09:35",
    [string]$DaysOfWeek = "Monday,Tuesday,Wednesday,Thursday,Friday"
)

$ErrorActionPreference = "Stop"

$days = $DaysOfWeek -split "," | ForEach-Object { $_.Trim() }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`""

$triggers = foreach ($day in $days) {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $day -At $RunTime
}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Principal $principal `
    -Settings $settings `
    -Force

Write-Host "Registered scheduled task '$TaskName' to run at $RunTime on $DaysOfWeek."
Write-Host "To run immediately for validation: Start-ScheduledTask -TaskName '$TaskName'"
