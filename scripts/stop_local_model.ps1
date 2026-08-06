$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExpectedServer = Join-Path $ProjectRoot "tools\llama.cpp\llama-server.exe"
$PidFile = Join-Path $ProjectRoot ".runtime\llama_server.pid"

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No managed local-model process is recorded."
    exit 0
}

$ServerPid = Get-Content -LiteralPath $PidFile
$Process = Get-Process -Id $ServerPid -ErrorAction SilentlyContinue
if ($Process) {
    if ($Process.Path -ne $ExpectedServer) {
        throw "PID $ServerPid does not belong to this project's llama-server."
    }
    Stop-Process -Id $ServerPid
    $Process.WaitForExit()
    Write-Host "Stopped local model (PID $ServerPid)."
}
else {
    Write-Host "The recorded local-model process is no longer running."
}

Remove-Item -LiteralPath $PidFile -Force
