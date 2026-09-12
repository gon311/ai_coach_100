$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidPath = Join-Path $ProjectRoot "logs\qwen3-server.pid"

if (-not (Test-Path -LiteralPath $PidPath -PathType Leaf)) {
    Write-Output "저장된 Qwen3 서버 PID가 없습니다."
    exit 0
}

$ServerPid = [int](Get-Content -LiteralPath $PidPath -Raw)
$Process = Get-Process -Id $ServerPid -ErrorAction SilentlyContinue
if ($null -ne $Process -and $Process.ProcessName -like "llama-server*") {
    Stop-Process -Id $ServerPid
    Write-Output "Qwen3 서버를 종료했습니다 (PID $ServerPid)."
} else {
    Write-Output "해당 PID의 llama-server가 실행 중이지 않습니다."
}
Remove-Item -LiteralPath $PidPath -Force
