param(
    [int]$Port = 8080,
    [int]$Threads = 8,
    [int]$ContextSize = 4096,
    [int]$GpuLayers = 0
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Server = Join-Path $ProjectRoot "tools\llama.cpp\llama-server.exe"
$Model = Join-Path $ProjectRoot "models\qwen3-4b\Qwen3-4B-Q4_K_M.gguf"
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$ApiKeyFile = Join-Path $RuntimeDir "copilot_api_key.txt"
$PidFile = Join-Path $RuntimeDir "llama_server.pid"
$StdoutLog = Join-Path $RuntimeDir "llama_server.stdout.log"
$StderrLog = Join-Path $RuntimeDir "llama_server.stderr.log"

if (-not (Test-Path -LiteralPath $Server)) {
    throw "llama-server was not found at $Server"
}
if (-not (Test-Path -LiteralPath $Model)) {
    throw "Qwen GGUF was not found at $Model"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $ApiKeyFile)) {
    [Guid]::NewGuid().ToString("N") | Set-Content -LiteralPath $ApiKeyFile -Encoding ascii
}

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
    $Existing = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
    if ($Existing -and $Existing.Path -eq $Server) {
        Write-Host "Local model is already running (PID $ExistingPid)."
        exit 0
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$Arguments = @(
    "-m", ('"' + $Model + '"'),
    "--alias", "Qwen3-4B-Q4_K_M.gguf",
    "--host", "127.0.0.1",
    "--port", $Port,
    "-c", $ContextSize,
    "-t", $Threads,
    "-ngl", $GpuLayers,
    "-np", "1",
    "--no-cont-batching",
    "--reasoning", "off",
    "--no-webui",
    "--cors-origins", "localhost",
    "--api-key-file", ('"' + $ApiKeyFile + '"')
)

$Process = Start-Process -FilePath $Server `
    -ArgumentList $Arguments `
    -WorkingDirectory (Split-Path -Parent $Server) `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -WindowStyle Hidden `
    -PassThru
$Process.Id | Set-Content -LiteralPath $PidFile -Encoding ascii

$ApiKey = Get-Content -LiteralPath $ApiKeyFile -Raw
$Headers = @{ Authorization = "Bearer $($ApiKey.Trim())" }
for ($Attempt = 1; $Attempt -le 45; $Attempt++) {
    if ($Process.HasExited) {
        throw "llama-server exited during startup. Check $StderrLog"
    }
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Headers $Headers -TimeoutSec 2 | Out-Null
        Write-Host "Qwen local model ready at http://127.0.0.1:$Port (PID $($Process.Id))."
        exit 0
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

throw "llama-server did not become ready within 45 seconds. Check $StderrLog"
