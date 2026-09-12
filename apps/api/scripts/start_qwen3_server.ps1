param(
    [int]$Port = 8080,
    [int]$ContextSize = 8192,
    [int]$GpuLayers = 99
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BundledModelPath = Join-Path $ProjectRoot "models\Qwen3-4B-Q4_K_M.gguf"
$ModelPath = if ($env:AI_FITNESS_MODEL_PATH) {
    $env:AI_FITNESS_MODEL_PATH
} else {
    $BundledModelPath
}
$LogDirectory = Join-Path $ProjectRoot "logs"
$PidPath = Join-Path $LogDirectory "qwen3-server.pid"
$StdoutPath = Join-Path $LogDirectory "qwen3-server.out.log"
$StderrPath = Join-Path $LogDirectory "qwen3-server.err.log"

if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw "Qwen3 4B Q4_K_M GGUF 모델을 찾을 수 없습니다: $ModelPath"
}

try {
    $RunningModels = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -TimeoutSec 2
    $RunningJson = $RunningModels | ConvertTo-Json -Depth 8
    if ($RunningJson -like "*Qwen3-4B-Q4_K_M.gguf*") {
        Write-Output "Qwen3 서버가 이미 실행 중입니다: http://127.0.0.1:$Port"
        exit 0
    }
    throw "포트 $Port 에 다른 모델 서버가 실행 중입니다. 해당 서버를 먼저 종료하세요."
} catch {
    if ($_.Exception.Message -like "*다른 모델 서버*") {
        throw
    }
    # 서버가 없을 때만 아래에서 새로 시작한다.
}

$LlamaServer = (Get-Command "llama-server.exe" -ErrorAction Stop).Source
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null

$Arguments = @(
    "--model", $ModelPath,
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--ctx-size", "$ContextSize", "--parallel", "1", "--jinja", "--reasoning", "off",
    "--n-gpu-layers", "$GpuLayers"
)

$Process = Start-Process `
    -FilePath $LlamaServer `
    -ArgumentList $Arguments `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $StdoutPath `
    -RedirectStandardError $StderrPath `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $PidPath -Value $Process.Id -Encoding ASCII
Write-Output "Qwen3 서버 시작 요청 완료 (PID $($Process.Id))"
Write-Output "모델을 메모리에 올리는 데 시간이 걸릴 수 있습니다."
Write-Output "준비 확인: http://127.0.0.1:$Port/v1/models"
Write-Output "로그: $StderrPath"
