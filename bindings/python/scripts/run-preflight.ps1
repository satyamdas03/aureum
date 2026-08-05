#Requires -Version 5.1
<#
.SYNOPSIS
    Preflight validation script for Aureum live paper trading.
.DESCRIPTION
    Loads a local .env file, sanity-checks Alpaca credentials, runs ``aureum live``
    in dry-run mode outside market hours, and prints a GO/NO-GO summary.  This
    script never submits real orders.
.PARAMETER EnvFile
    Path to a key=value environment file.
.PARAMETER Strategy
    Path to the strategy YAML.
.PARAMETER Data
    Path to the recent price CSV.
.PARAMETER CertificateDir
    Directory where the preflight certificate JSON is written.
.PARAMETER MaxTotalInvestedPct
    Maximum total invested notional as a fraction of equity (0.0 means use
    the strategy's configured value).
#>
param(
    [string]$EnvFile = "$PSScriptRoot\.env",
    [string]$Strategy = "$PSScriptRoot\..\..\examples\strategies\momentum.yaml",
    [string]$Data = "$PSScriptRoot\..\..\examples\data\synthetic_prices.csv",
    [string]$CertificateDir = "$PSScriptRoot\..\..\..\live-certificates",
    [double]$MaxTotalInvestedPct = 0.0
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[Aureum Preflight] $Message" -ForegroundColor Cyan
}

function Write-Result {
    param([string]$Status, [string]$Message)
    if ($Status -eq "GO") {
        Write-Host "[Aureum Preflight] GO: $Message" -ForegroundColor Green
    } else {
        Write-Host "[Aureum Preflight] NO-GO: $Message" -ForegroundColor Red
    }
}

# ---------------------------------------------------------------------------
# Ensure output directory exists
# ---------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $CertificateDir | Out-Null
$certDir = Resolve-Path $CertificateDir
$timestamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$certPath = Join-Path $certDir "preflight-$timestamp.json"

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
} else {
    Write-Step "No .env file found at $EnvFile; relying on process environment"
}

if (-not $env:ALPACA_API_KEY -or -not $env:ALPACA_SECRET_KEY) {
    Write-Result -Status "NO-GO" -Message "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in $EnvFile or the environment."
    exit 1
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
# Preflight dry-run invocation
# ---------------------------------------------------------------------------
$liveArgs = @(
    "live",
    (Resolve-Path $Strategy).Path,
    "--data", (Resolve-Path $Data).Path,
    "--certificate", $certPath,
    "--paper",
    "--dry-run",
    "--ignore-market-hours"
)
if ($MaxTotalInvestedPct -gt 0.0) {
    $liveArgs += "--max-total-invested-pct"
    $liveArgs += $MaxTotalInvestedPct
}

Write-Step "Running aureum live dry-run preflight"
& python -m aureum.cli @liveArgs
$exitCode = $LASTEXITCODE

# ---------------------------------------------------------------------------
# Validate output
# ---------------------------------------------------------------------------
$go = $true
$failures = @()

if ($exitCode -ne 0) {
    $go = $false
    $failures += "aureum live exited with code $exitCode"
}

if (-not (Test-Path $certPath)) {
    $go = $false
    $failures += "certificate file was not written to $certPath"
} else {
    $certText = Get-Content $certPath -Raw
    if ($certText -notmatch '"live_mode"\s*:\s*"paper-dry-run"') {
        $go = $false
        $failures += "certificate live_mode is not paper-dry-run"
    }
    if ($certText -match '"errors"\s*:\s*\[\s*\]') {
        # no errors
    } elseif ($certText -match '"errors"') {
        $go = $false
        $failures += "certificate contains errors"
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host "----------------------------------------"
if ($go) {
    Write-Result -Status "GO" -Message "Preflight passed. Safe to run with -SubmitOrders during market hours."
    Write-Step "Certificate: $certPath"
    exit 0
} else {
    Write-Result -Status "NO-GO" -Message "Preflight failed. Details:"
    foreach ($failure in $failures) {
        Write-Host "  - $failure" -ForegroundColor Red
    }
    exit 1
}
