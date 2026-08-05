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
.PARAMETER SubmitOrders
    Register the task to submit real orders. The default task is dry-run.
.PARAMETER MaxTotalInvestedPct
    Maximum total invested notional as a fraction of equity (0.0 means use
    the strategy's configured value).
.PARAMETER IgnoreMarketHours
    Allow the task to run outside market hours.
#>
param(
    [string]$TaskName = "AureumDailyPaperTrading",
    [string]$ScriptPath = "$PSScriptRoot\aureum-daily-task.ps1",
    [string]$Strategy = "$PSScriptRoot\..\..\examples\strategies\hero_phase4_live.yaml",
    [string]$Data = "$PSScriptRoot\..\..\examples\data\alpaca_tech_snapshot.csv",
    [string]$RunTime = "23:35",
    [string]$DaysOfWeek = "Monday,Tuesday,Wednesday,Thursday,Friday",
    [switch]$SubmitOrders,
    [double]$MaxTotalInvestedPct = 0.0,
    [switch]$IgnoreMarketHours
)

$ErrorActionPreference = "Stop"

$days = $DaysOfWeek -split "," | ForEach-Object { $_.Trim() }

$resolvedScript = Resolve-Path $ScriptPath
$resolvedStrategy = Resolve-Path $Strategy
$resolvedData = Resolve-Path $Data

$argumentString = "-ExecutionPolicy Bypass -File `"$($resolvedScript.Path)`" -Strategy `"$($resolvedStrategy.Path)`" -Data `"$($resolvedData.Path)`""
if ($SubmitOrders) { $argumentString += " -SubmitOrders" }
if ($MaxTotalInvestedPct -gt 0.0) {
    $argumentString += " -MaxTotalInvestedPct $MaxTotalInvestedPct"
}
if ($IgnoreMarketHours) { $argumentString += " -IgnoreMarketHours" }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $argumentString

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

$mode = if ($SubmitOrders) { "live paper" } else { "dry-run" }
Write-Host "Registered scheduled task '$TaskName' to run at $RunTime local time on $DaysOfWeek."
Write-Host "Strategy: $resolvedStrategy"
Write-Host "Data:     $resolvedData"
Write-Host "Mode:     $mode"
Write-Host "NOTE:    $RunTime local time is 09:35 US/Eastern (market open + 5 minutes) when this machine is in AEST."
Write-Host "To run immediately for validation: Start-ScheduledTask -TaskName '$TaskName'"
