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
    Run even when the market is closed (useful for dry-run validation).
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

function Write-Step {
    param([string]$Message)
    Write-Host "[Aureum] $Message" -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------
if (Test-Path $KillSwitch) {
    Write-Step "Kill switch present at $KillSwitch; exiting without action."
    exit 0
}

# ---------------------------------------------------------------------------
# Resolve repo root and load .env
# ---------------------------------------------------------------------------
$repoRoot = Resolve-Path "$PSScriptRoot\..\..\.."

if (Test-Path $EnvFile) {
    Write-Step "Loading environment from $EnvFile"
    Get-Content $EnvFile |
        Where-Object { $_ -match '^\s*([^#\s][^=]*)\s*=\s*(.*)$' } |
        ForEach-Object {
            $name = $_.Matches.Groups[1].Value.Trim()
            $value = $_.Matches.Groups[2].Value.Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
}

if (-not $env:ALPACA_API_KEY -or -not $env:ALPACA_SECRET_KEY) {
    throw "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in $EnvFile or the environment."
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
# Ensure output directory and build certificate path
# ---------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $CertificateDir | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$certPath = Join-Path $CertificateDir "live-$timestamp.json"

$sharedArgs = @("--paper")
if ($IgnoreMarketHours) { $sharedArgs += "--ignore-market-hours" }

# ---------------------------------------------------------------------------
# Account snapshot (always run first as a health check)
# ---------------------------------------------------------------------------
Write-Step "Running account snapshot"
& python -m aureum.cli account @sharedArgs
if ($LASTEXITCODE -ne 0) { throw "aureum account failed with exit code $LASTEXITCODE" }

# ---------------------------------------------------------------------------
# Live rebalance
# ---------------------------------------------------------------------------
$liveArgs = @(
    "live",
    (Resolve-Path $Strategy).Path,
    "--data", (Resolve-Path $Data).Path,
    "--certificate", $certPath
) + $sharedArgs
if ($DryRun) { $liveArgs += "--dry-run" }

Write-Step "Running aureum live"
& python -m aureum.cli @liveArgs
if ($LASTEXITCODE -ne 0) { throw "aureum live failed with exit code $LASTEXITCODE" }

# ---------------------------------------------------------------------------
# Optional git commit/push
# ---------------------------------------------------------------------------
if ($env:AUREUM_GIT_PUSH -eq "true") {
    Write-Step "Committing and pushing state"
    git add memory/ $CertificateDir
    git commit -m "aureum: daily live run $timestamp" --allow-empty
    git push origin main
}

Write-Step "Daily task complete. Certificate written to $certPath"
