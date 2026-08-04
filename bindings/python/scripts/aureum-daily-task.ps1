#Requires -Version 5.1
<#
.SYNOPSIS
    Daily Aureum live paper-trading task for Windows Task Scheduler.
.DESCRIPTION
    Loads a local .env file, sanity-checks Alpaca credentials, runs an account
    snapshot, then runs the configured strategy via ``aureum live``.  If
    AUREUM_GIT_PUSH is true, it commits memory/ and live-certificates/.
.PARAMETER DryRun
    Print intended orders without submitting them.
.PARAMETER IgnoreMarketHours
    Run even when the market is closed (useful for dry-run validation). When
    not set, the task will abort if the market is closed, which is the safe
    default for real money-adjacent paper trading.
.PARAMETER EnvFile
    Path to a key=value environment file.
.PARAMETER Strategy
    Path to the strategy YAML.
.PARAMETER Data
    Path to the recent price CSV.
.PARAMETER CertificateDir
    Directory where the live certificate JSON is written.
.PARAMETER KillSwitch
    Path to a kill-switch file; if it exists, the task exits silently.
#>
param(
    [string]$EnvFile = "$PSScriptRoot\.env",
    [string]$Strategy = "$PSScriptRoot\..\..\examples\strategies\momentum.yaml",
    [string]$Data = "$PSScriptRoot\..\..\examples\data\synthetic_prices.csv",
    [string]$CertificateDir = "$PSScriptRoot\..\..\..\live-certificates",
    [string]$KillSwitch = "$PSScriptRoot\kill.switch",
    [switch]$DryRun,
    [switch]$IgnoreMarketHours
)

$ErrorActionPreference = "Stop"

$script:exitCode = 0
$script:certPath = $null

Write-Host "[Aureum] Starting daily task from PSScriptRoot=$PSScriptRoot" -ForegroundColor Cyan

function Write-Step {
    param([string]$Message)
    Write-Host "[Aureum] $Message" -ForegroundColor Cyan
}

function Write-Log {
    param(
        [string]$Message,
        [int]$ExitCode = $script:exitCode,
        [string]$CertificatePath = $script:certPath
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$timestamp | $Message | exit_code=$ExitCode"
    if ($CertificatePath) {
        $line += " | certificate=$CertificatePath"
    }
    Add-Content -Path $script:logPath -Value $line -Encoding utf8
}

# ---------------------------------------------------------------------------
# Ensure output directory and log file exist
# ---------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $CertificateDir | Out-Null
$certDir = Resolve-Path $CertificateDir
$script:logPath = Join-Path $certDir "aureum-daily-task.log"
if (-not (Test-Path $script:logPath)) {
    New-Item -ItemType File -Path $script:logPath -Force | Out-Null
}

# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------
if (Test-Path $KillSwitch) {
    $msg = "Kill switch present at $KillSwitch; exiting without action."
    Write-Step $msg
    Write-Log -Message $msg
    exit 0
}

# ---------------------------------------------------------------------------
# Resolve repo root and load .env
# ---------------------------------------------------------------------------
$repoRoot = Resolve-Path "$PSScriptRoot\..\..\.."

if (Test-Path $EnvFile) {
    Write-Step "Loading environment from $EnvFile"
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#\s][^=]*)\s*=\s*(.*)$') {
            $name = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Write-Log -Message "Loaded environment from $EnvFile"
}

if (-not $env:ALPACA_API_KEY -or -not $env:ALPACA_SECRET_KEY) {
    $msg = "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in $EnvFile or the environment."
    Write-Log -Message $msg -ExitCode 1
    throw $msg
}

# ---------------------------------------------------------------------------
# Activate virtual environment if present
# ---------------------------------------------------------------------------
$venv = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venv) {
    Write-Step "Activating virtual environment: $venv"
    & $venv
}

Set-Location $repoRoot

# ---------------------------------------------------------------------------
# Build certificate path in the resolved certificate directory
# ---------------------------------------------------------------------------
$timestamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$script:certPath = Join-Path $certDir "live-$timestamp.json"

$sharedArgs = @("--paper")
if ($DryRun -or $IgnoreMarketHours) { $sharedArgs += "--ignore-market-hours" }

# ---------------------------------------------------------------------------
# Account snapshot (always run first as a health check)
# ---------------------------------------------------------------------------
Write-Step "Running account snapshot"
& python -m aureum.cli account @sharedArgs
$script:exitCode = $LASTEXITCODE
if ($script:exitCode -ne 0) {
    $msg = "aureum account failed with exit code $script:exitCode"
    Write-Log -Message $msg -ExitCode $script:exitCode
    throw $msg
}
Write-Log -Message "Account snapshot completed" -ExitCode $script:exitCode

# ---------------------------------------------------------------------------
# Live rebalance
# ---------------------------------------------------------------------------
$liveArgs = @(
    "live",
    (Resolve-Path $Strategy).Path,
    "--data", (Resolve-Path $Data).Path,
    "--certificate", $script:certPath
) + $sharedArgs
if ($DryRun) { $liveArgs += "--dry-run" }

# If not a dry run, respect market hours unless explicitly overridden.
if (-not $DryRun -and -not $IgnoreMarketHours) {
    Write-Step "Market-hours check enabled; task will abort if market is closed."
}

Write-Step "Running aureum live"
& python -m aureum.cli @liveArgs
$script:exitCode = $LASTEXITCODE
if ($script:exitCode -ne 0) {
    $msg = "aureum live failed with exit code $script:exitCode"
    Write-Log -Message $msg -ExitCode $script:exitCode -CertificatePath $script:certPath
    throw $msg
}
Write-Log -Message "Live rebalance completed" -ExitCode $script:exitCode -CertificatePath $script:certPath

# ---------------------------------------------------------------------------
# Optional git commit/push
# ---------------------------------------------------------------------------
if ($env:AUREUM_GIT_PUSH -eq "true") {
    Write-Step "Committing and pushing state"
    git add memory/ $CertificateDir
    git commit -m "aureum: daily live run $timestamp" --allow-empty
    git push origin main
    Write-Log -Message "Git commit/push completed" -ExitCode $script:exitCode -CertificatePath $script:certPath
}

$doneMsg = "Daily task complete. Certificate written to $script:certPath"
Write-Step $doneMsg
Write-Log -Message "Daily task complete" -ExitCode $script:exitCode -CertificatePath $script:certPath
