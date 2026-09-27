<#
AgriPulse - one-command local run for Windows (no Docker, no PostgreSQL needed).

    powershell -ExecutionPolicy Bypass -File .\run-local.ps1            # first run sets everything up
    powershell -ExecutionPolicy Bypass -File .\run-local.ps1 -NoDemo    # skip the synthetic demo workspace
    powershell -ExecutionPolicy Bypass -File .\run-local.ps1 -Reset     # delete the local database and start fresh

Opens three windows: API (port 8000), ingestion scheduler, web app (port 3000).
Data is stored in backend\agripulse.db (SQLite). For PostgreSQL, set DATABASE_URL in backend\.env.

Real mandi prices need a free data.gov.in key. Put it in backend\.env yourself:
    DATA_GOV_IN_API_KEY=your-key
It stays on the server side and is never sent to the browser. Weather (Open-Meteo) needs no key.

Requires Python 3.11+ and Node.js 20+.
#>
param([switch]$Reset, [switch]$NoDemo, [switch]$SkipBuild)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# --- prerequisites -----------------------------------------------------------
Step "Checking prerequisites"
$Py = $null
foreach ($cand in @("python", "py")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        $ver = & $cand -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$ver -ge [version]"3.11") { $Py = $cand; break }
    }
}
if (-not $Py) { Fail "Python 3.11+ not found. Install it from https://www.python.org/downloads/ (tick 'Add to PATH')." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js not found. Install Node 20+ from https://nodejs.org/." }
Write-Host "Python $ver ($Py), Node $(node --version)"

# --- backend -----------------------------------------------------------------
Step "Setting up the backend"
Set-Location $Backend
$VenvPy = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) { & $Py -m venv .venv; if ($LASTEXITCODE) { Fail "Could not create the virtual environment." } }
& $VenvPy -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE) { Fail "pip install failed." }

$EnvFile = Join-Path $Backend ".env"
if (-not (Test-Path $EnvFile)) {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes)
    (Get-Content (Join-Path $Backend ".env.example")) `
        -replace '^DATABASE_URL=.*', 'DATABASE_URL=sqlite:///./agripulse.db' `
        -replace '^JWT_SECRET=.*', "JWT_SECRET=$secret" |
        Set-Content -Encoding utf8 $EnvFile
    Write-Host "Created backend\.env (SQLite, random JWT secret)."
}
$hasKey = (Select-String -Path $EnvFile -Pattern '^DATA_GOV_IN_API_KEY=\S+' -Quiet)
if (-not $hasKey) {
    Write-Host "Note: DATA_GOV_IN_API_KEY is empty - mandi prices will show 'Not configured' (weather still works)." -ForegroundColor Yellow
}

if ($Reset) {
    Get-ChildItem $Backend -Filter "agripulse.db*" -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host "Local database deleted."
}
& $VenvPy -m alembic upgrade head
if ($LASTEXITCODE) { Fail "Database migration failed." }
if (-not $NoDemo) { & $VenvPy -m app.seed }

# --- frontend ----------------------------------------------------------------
Step "Setting up the web app"
Set-Location $Frontend
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { npm ci; if ($LASTEXITCODE) { Fail "npm ci failed." } }
if (-not $SkipBuild) { npm run build; if ($LASTEXITCODE) { Fail "Frontend build failed." } }

# --- start -------------------------------------------------------------------
Step "Starting AgriPulse"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='AgriPulse API'; Set-Location '$Backend'; & '$VenvPy' -m uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='AgriPulse scheduler'; Set-Location '$Backend'; & '$VenvPy' -m app.scheduler"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='AgriPulse web'; Set-Location '$Frontend'; npm start"

Write-Host "Waiting for the web app..."
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://localhost:3000/login" | Out-Null; break } catch { Start-Sleep 1 }
}
Start-Process "http://localhost:3000"
Write-Host "`nAgriPulse is running at http://localhost:3000" -ForegroundColor Green
if (-not $NoDemo) { Write-Host "Demo sign-in: ops@agriflow.demo / Demo@1234 (synthetic demo workspace)" }
Write-Host "Close the three AgriPulse windows to stop it."
