param(
    [ValidateSet("deterministic", "llama_cpp_server")]
    [string]$Provider = "deterministic",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment not found at $Python"
}

$env:COPILOT_PROVIDER = $Provider
Set-Location -LiteralPath $ProjectRoot
& $Python -m src.copilot.web_app --host 127.0.0.1 --port $Port
