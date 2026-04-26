<#
.SYNOPSIS
    DOME 4.0 Initialization Script
    
.DESCRIPTION
    Run this when you open a new session to:
    1. Sync the latest DOME_CORE code from Git
    2. Verify Supabase cloud connectivity
    3. Register the local agent with a heartbeat
    4. Display system status
    
.USAGE
    # From any terminal:
    . D:\DOME_CORE\scripts\dome_init.ps1
    
    # Or add to your PowerShell profile for auto-run:
    # Add-Content $PROFILE ". D:\DOME_CORE\scripts\dome_init.ps1"
#>

$ErrorActionPreference = "Continue"

# ── Banner ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║          DOME 4.0 — Initializing         ║" -ForegroundColor Cyan
Write-Host "  ║    Distributed Agentic Operating System   ║" -ForegroundColor DarkCyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Locate DOME_CORE ──────────────────────────────────────────────
$DOME_ROOT = $null
$candidates = @(
    $env:DOME_CORE_ROOT,
    "D:\DOME_CORE",
    "G:\DOME_CORE"
)

foreach ($path in $candidates) {
    if ($path -and (Test-Path $path)) {
        $DOME_ROOT = $path
        break
    }
}

if (-not $DOME_ROOT) {
    Write-Host "  [ERROR] DOME_CORE not found. Set DOME_CORE_ROOT env var." -ForegroundColor Red
    return
}

$env:DOME_CORE_ROOT = $DOME_ROOT
Write-Host "  [1/5] DOME_CORE located: $DOME_ROOT" -ForegroundColor Green

# ── Step 2: Git Sync ──────────────────────────────────────────────────────
$gitDir = Join-Path $DOME_ROOT ".git"
if (Test-Path $gitDir) {
    Write-Host "  [2/5] Git sync..." -ForegroundColor Yellow -NoNewline
    Push-Location $DOME_ROOT
    try {
        $gitStatus = git status --porcelain 2>&1
        $pullResult = git pull --rebase --quiet 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host " ✓ Up to date" -ForegroundColor Green
        } else {
            Write-Host " ⚠ Pull issue (working offline)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host " ⚠ Git not available (offline mode)" -ForegroundColor Yellow
    }
    Pop-Location
} else {
    Write-Host "  [2/5] Git: Not initialized (run 'git init' in $DOME_ROOT)" -ForegroundColor Yellow
}

# ── Step 3: Load Environment ──────────────────────────────────────────────
$envFile = Join-Path $DOME_ROOT ".env"
if (Test-Path $envFile) {
    Write-Host "  [3/5] Loading .env..." -ForegroundColor Yellow -NoNewline
    $envCount = 0
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.+)$") {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
            $envCount++
        }
    }
    Write-Host " ✓ $envCount variables loaded" -ForegroundColor Green
} else {
    Write-Host "  [3/5] No .env found. Copy .env.template to .env and fill in values." -ForegroundColor Yellow
}

# ── Step 4: Detect Environment ────────────────────────────────────────────
$domeEnv = if ($env:DOME_ENVIRONMENT) { $env:DOME_ENVIRONMENT } 
           elseif ($DOME_ROOT.StartsWith("D:")) { "home" } 
           else { "work" }
Write-Host "  [4/5] Environment: $($domeEnv.ToUpper())" -ForegroundColor Cyan

# ── Step 5: Supabase Connectivity ─────────────────────────────────────────
if ($env:DOME_SUPABASE_URL -and $env:DOME_SUPABASE_KEY) {
    Write-Host "  [5/5] Supabase..." -ForegroundColor Yellow -NoNewline
    
    try {
        $checkScript = @"
import sys
sys.path.insert(0, r'$DOME_ROOT')
from core.supabase_client import check_connection
status = check_connection()
if status['connected']:
    print(f"CONNECTED|{status['agent_count']}")
else:
    print(f"FAILED|{status['error']}")
"@
        $result = python -c $checkScript 2>&1
        if ($result -match "CONNECTED\|(\d+)") {
            $agentCount = $matches[1]
            Write-Host " ✓ Connected ($agentCount agents registered)" -ForegroundColor Green
        } else {
            Write-Host " ⚠ $result" -ForegroundColor Yellow
        }
    } catch {
        Write-Host " ⚠ Python check failed (install supabase: pip install supabase)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [5/5] Supabase: Not configured (set DOME_SUPABASE_URL and DOME_SUPABASE_KEY)" -ForegroundColor Yellow
}

# ── Summary ───────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌─────────────────────────────────────────┐" -ForegroundColor DarkGray
Write-Host "  │  DOME 4.0 Ready                          │" -ForegroundColor White
Write-Host "  │  Root:  $DOME_ROOT" -ForegroundColor DarkGray
Write-Host "  │  Env:   $($domeEnv.ToUpper())" -ForegroundColor DarkGray
Write-Host "  │  Python: $(python --version 2>&1)" -ForegroundColor DarkGray
Write-Host "  └─────────────────────────────────────────┘" -ForegroundColor DarkGray
Write-Host ""
