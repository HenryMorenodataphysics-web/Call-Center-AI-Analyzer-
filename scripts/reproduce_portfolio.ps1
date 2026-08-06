param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $PythonPath) {
    $candidate = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $candidate) {
        $PythonPath = $candidate
    } else {
        $PythonPath = "python"
    }
}

Push-Location $projectRoot
try {
    & $PythonPath "scripts\reproduce_portfolio.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Portfolio reproduction failed. See reports/reproducibility_report.md."
    }
} finally {
    Pop-Location
}
