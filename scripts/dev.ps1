param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("setup", "audit", "train", "run-pipeline", "test", "run-api", "run-ui", "acceptance", "e2e-synthetic", "real-datasets")]
    [string]$Task
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($Task -eq "setup") {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        py -3.13 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Python 3.13 virtual environment." }
    }
    $Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    if (Test-Path "requirements.lock") {
        & $Python -m pip install -r requirements.lock
    } else {
        & $Python -m pip install -r requirements.txt
    }
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    if (-not (Test-Path ".env")) { Copy-Item .env.example .env }

    if (Test-Path "dashboard\package.json") {
        Write-Host "Installing dashboard npm dependencies..."
        Push-Location dashboard
        npm install
        Pop-Location
    }
    Write-Host "Setup complete. Configure .env and run .\scripts\dev.ps1 test or run-api."
    return
}

$Python = if (Test-Path ".venv\Scripts\python.exe") { Join-Path $RepoRoot ".venv\Scripts\python.exe" } else { "python" }
$env:PYTHONPATH = $RepoRoot

switch ($Task) {
    "audit" { & $Python scripts/audit_datasets.py --root $RepoRoot }
    "train" { & $Python -m src.ml.delay.run --root $RepoRoot }
    "run-pipeline" { & $Python -m src.core.pipeline --root $RepoRoot --retry }
    "test" {
        Write-Host "Running backend tests (pytest)..."
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Backend test suite failed." }
        if (Test-Path "dashboard\package.json") {
            Write-Host "Running frontend tests (vitest)..."
            Push-Location dashboard
            npm test -- --run
            Pop-Location
        }
    }
    "acceptance" {
        Write-Host "Running Stage 10 Acceptance Test Suite (Scenarios 1-10)..."
        & $Python -m pytest tests/test_stage10_scenarios.py -v
    }
    "e2e-synthetic" {
        Write-Host "Running End-to-End Synthetic Company Lifecycle..."
        & $Python scripts/run_e2e_synthetic.py
    }
    "real-datasets" {
        Write-Host "Running Real Datasets In-Memory Validation & Timing..."
        & $Python scripts/run_real_datasets.py
    }
    "run-api" { & $Python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 }
    "run-ui" {
        if (-not (Test-Path "dashboard\package.json")) { throw "dashboard/package.json not found." }
        Push-Location dashboard
        npm run dev
        Pop-Location
    }
}
if ($LASTEXITCODE -ne 0) { throw "Task '$Task' failed with exit code $LASTEXITCODE." }
