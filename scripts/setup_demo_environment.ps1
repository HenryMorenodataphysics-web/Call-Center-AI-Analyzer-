param(
    [string]$EnvironmentPath = ".venv"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentRoot = Join-Path $projectRoot $EnvironmentPath
$pythonPath = Join-Path $environmentRoot "Scripts\python.exe"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher (py.exe) was not found. Install Python 3.12 and retry."
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3.12 -m venv $environmentRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python 3.12 virtual environment."
    }
}

& $pythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed."
}

& $pythonPath -m pip install -r (Join-Path $projectRoot "requirements-demo.lock.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Portfolio demo dependency installation failed."
}

Write-Host "Portfolio demo environment ready: $pythonPath"
Write-Host "Run .\scripts\reproduce_portfolio.ps1 to rebuild and validate the demo."
