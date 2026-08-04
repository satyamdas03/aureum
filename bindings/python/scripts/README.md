# Aureum Windows Task Scheduler integration

This folder contains PowerShell scripts to run Aureum live paper-trading
rebalances from the local machine via **Windows Task Scheduler**.

## Quick start

1. Copy `.env.example` to `.env` and fill in your Alpaca paper credentials.
2. Run a manual dry-run from this folder:

   ```powershell
   .\aureum-daily-task.ps1 -DryRun -IgnoreMarketHours
   ```

3. Register the daily scheduled task (run as Administrator):

   ```powershell
   .\register-scheduled-task.ps1 -RunTime "09:15"
   ```

4. Inspect the scheduled task:

   ```powershell
   Get-ScheduledTask -TaskName "AureumDailyPaperTrading"
   Start-ScheduledTask -TaskName "AureumDailyPaperTrading"
   ```

## Safety defaults

- `--paper` is hard-coded in the task; live trading requires explicit code
  changes and `AUREUM_FORCE_LIVE=true`.
- A kill-switch file (`kill.switch` by default) makes the task exit silently.
- Account snapshot is always run first as a health check.
- Git push is opt-in via `AUREUM_GIT_PUSH=true`.

## Outputs

Each run writes a `LiveTradingCertificate` JSON to `..\..\..\live-certificates\`
(by default) with the timestamped filename `live-YYYY-MM-DD-HHMM.json`.
