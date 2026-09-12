param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status",
    [int]$WebPort = 8501,
    [int]$ModelPort = 8080,
    [ValidateRange(4096, 32768)]
    [int]$ContextSize = 8192,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = if ($env:AI_FITNESS_RUNTIME_ROOT) {
    $env:AI_FITNESS_RUNTIME_ROOT
} else {
    "C:\ai_fitness_qwen3_runtime"
}
$LogDirectory = Join-Path $RuntimeRoot "logs"
$OutputDirectory = Join-Path $RuntimeRoot "outputs"
$WebPidPath = Join-Path $RuntimeRoot "web.pid"
$ModelPidPath = Join-Path $RuntimeRoot "model.pid"
$WebUrl = "http://127.0.0.1:$WebPort"
$ModelUrl = "http://127.0.0.1:$ModelPort"

function Get-ListeningProcessId([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $connection) { return $null }
    return [int]$connection.OwningProcess
}

function Test-WebReady {
    try {
        $health = Invoke-RestMethod -Uri "$WebUrl/api/health" -TimeoutSec 3
        return $health.status -eq "ok"
    } catch { return $false }
}

function Test-ModelReady {
    try {
        $models = Invoke-RestMethod -Uri "$ModelUrl/v1/models" -TimeoutSec 3
        return (($models | ConvertTo-Json -Depth 8) -like "*Qwen3-4B-Q4_K_M.gguf*")
    } catch { return $false }
}

function Stop-OwnedProcess([string]$PidPath, [string]$ExpectedName, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PidPath -PathType Leaf)) {
        Write-Output "$Label PID 기록이 없습니다."
        return
    }
    $savedPid = [int](Get-Content -LiteralPath $PidPath -Raw)
    $process = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
    if ($null -ne $process -and $process.ProcessName -like $ExpectedName) {
        & taskkill.exe /PID $savedPid /T /F | Out-Null
        Write-Output "$Label 종료 완료 (PID $savedPid)"
    } else {
        Write-Output "$Label 프로세스가 이미 종료되어 있습니다."
    }
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
}

function Sync-ChromaIndex {
    $bundleChroma = Join-Path $ProjectRoot "artifacts\chroma"
    $runtimeChroma = Join-Path $RuntimeRoot "chroma"
    $bundleMarker = Join-Path $bundleChroma "BUILD_COMPLETE.json"
    $runtimeMarker = Join-Path $runtimeChroma "BUILD_COMPLETE.json"
    if (-not (Test-Path -LiteralPath $bundleMarker -PathType Leaf)) {
        throw "배포용 Chroma 인덱스를 찾을 수 없습니다: $bundleChroma"
    }
    if (Test-Path -LiteralPath $runtimeMarker -PathType Leaf) {
        $bundleHash = (Get-FileHash -LiteralPath $bundleMarker -Algorithm SHA256).Hash
        $runtimeHash = (Get-FileHash -LiteralPath $runtimeMarker -Algorithm SHA256).Hash
        if ($bundleHash -eq $runtimeHash) {
            Write-Output "검색 인덱스 준비 완료"
            return
        }
        throw "실행 캐시에 다른 버전의 검색 인덱스가 있습니다: $runtimeChroma"
    }
    if (Test-Path -LiteralPath $runtimeChroma) {
        throw "완성되지 않은 검색 인덱스 캐시가 있습니다: $runtimeChroma"
    }
    Write-Output "첫 실행용 검색 인덱스를 준비합니다. 한 번만 복사되며 잠시 걸릴 수 있습니다."
    Copy-Item -LiteralPath $bundleChroma -Destination $runtimeChroma -Recurse
    if (-not (Test-Path -LiteralPath $runtimeMarker -PathType Leaf)) {
        throw "검색 인덱스 복사가 완료되지 않았습니다."
    }
    Write-Output "검색 인덱스 준비 완료"
}

function Find-Python {
    if ($env:AI_FITNESS_PYTHON -and (Test-Path -LiteralPath $env:AI_FITNESS_PYTHON -PathType Leaf)) {
        return $env:AI_FITNESS_PYTHON
    }
    $runtimePython = Join-Path $RuntimeRoot "venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $runtimePython -PathType Leaf) { return $runtimePython }
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    $pythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) { return $pythonCommand.Source }
    throw "Python을 찾을 수 없습니다. 먼저 SETUP_AI_FITNESS_SERVER.cmd를 실행해 주세요."
}

function Start-Model {
    if (Test-ModelReady) {
        $runningPid = Get-ListeningProcessId $ModelPort
        if ($null -ne $runningPid) { Set-Content -LiteralPath $ModelPidPath -Value $runningPid -Encoding ASCII }
        Write-Output "Qwen3 모델 서버가 이미 준비되어 있습니다."
        return
    }

    if ($env:AI_FITNESS_MODEL_PATH -and (Test-Path -LiteralPath $env:AI_FITNESS_MODEL_PATH -PathType Leaf)) {
        $modelPath = $env:AI_FITNESS_MODEL_PATH
    } else {
        $modelPath = Join-Path $ProjectRoot "models\Qwen3-4B-Q4_K_M.gguf"
    }
    if (-not $modelPath -or -not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
        throw "Qwen3 모델을 찾을 수 없습니다. models\Qwen3-4B-Q4_K_M.gguf를 확인해 주세요."
    }

    $bundledLlamaServer = Join-Path $ProjectRoot "runtime\llama\llama-server.exe"
    if ($env:AI_FITNESS_LLAMA_SERVER -and (Test-Path -LiteralPath $env:AI_FITNESS_LLAMA_SERVER -PathType Leaf)) {
        $llamaServer = $env:AI_FITNESS_LLAMA_SERVER
    } elseif (Test-Path -LiteralPath $bundledLlamaServer -PathType Leaf) {
        $llamaServer = $bundledLlamaServer
    } else {
        $llamaCommand = Get-Command "llama-server.exe" -ErrorAction SilentlyContinue
        if ($null -eq $llamaCommand) {
            throw "llama-server.exe를 찾을 수 없습니다. 배포 폴더의 runtime\llama를 확인해 주세요."
        }
        $llamaServer = $llamaCommand.Source
    }
    $gpuLayers = if ($env:AI_FITNESS_GPU_LAYERS) { $env:AI_FITNESS_GPU_LAYERS } else { "99" }
    $arguments = @(
        "--model", ('"{0}"' -f $modelPath), "--host", "127.0.0.1",
        "--port", "$ModelPort", "--ctx-size", "$ContextSize", "--parallel", "1", "--jinja", "--reasoning", "off", "--n-gpu-layers", "$gpuLayers"
    )
    $process = Start-Process -FilePath $llamaServer -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput (Join-Path $LogDirectory "model.out.log") `
        -RedirectStandardError (Join-Path $LogDirectory "model.err.log") `
        -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $ModelPidPath -Value $process.Id -Encoding ASCII
    Write-Output "Qwen3 모델을 준비하고 있습니다 (PID $($process.Id))."

    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-ModelReady) { Write-Output "Qwen3 모델 준비 완료"; return }
        Start-Sleep -Seconds 2
    }
    throw "Qwen3 모델 서버가 준비되지 않았습니다. $LogDirectory\model.err.log를 확인해 주세요."
}

function Start-Web {
    if (Test-WebReady) {
        $runningPid = Get-ListeningProcessId $WebPort
        if ($null -ne $runningPid) { Set-Content -LiteralPath $WebPidPath -Value $runningPid -Encoding ASCII }
        Write-Output "웹 서버가 이미 준비되어 있습니다: $WebUrl"
        return
    }

    $python = Find-Python
    $sitePackages = Join-Path $env:USERPROFILE "Jupyter\.venv\Lib\site-packages"
    # A base Python without the packages is a normal first-run condition.
    # Do not let ErrorActionPreference stop us before the bundled fallback
    # site-packages location has been tried.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $python -c "import fastapi,uvicorn,chromadb,sentence_transformers,pydantic" 2>$null
    $moduleCheckExitCode = $LASTEXITCODE
    if ($moduleCheckExitCode -ne 0 -and (Test-Path -LiteralPath $sitePackages -PathType Container)) {
        $env:PYTHONPATH = $sitePackages
        & $python -c "import fastapi,uvicorn,chromadb,sentence_transformers,pydantic" 2>$null
        $moduleCheckExitCode = $LASTEXITCODE
    }
    $ErrorActionPreference = $previousErrorActionPreference
    if ($moduleCheckExitCode -ne 0) {
        throw "Python 필수 패키지가 없습니다. 먼저 SETUP_AI_FITNESS_SERVER.cmd를 실행해 주세요."
    }
    $env:AI_FITNESS_RUNTIME_ROOT = $RuntimeRoot
    $env:AI_FITNESS_ARTIFACTS_DIR = Join-Path $ProjectRoot "artifacts"
    $env:AI_FITNESS_CHROMA_DIR = Join-Path $RuntimeRoot "chroma"
    $env:AI_FITNESS_OUTPUT_DIR = $OutputDirectory
    $env:QWEN3_BASE_URL = $ModelUrl
    $arguments = @(
        "-m", "uvicorn", "fitness_web_server:app", "--app-dir", ('"{0}"' -f $PSScriptRoot),
        "--host", "127.0.0.1", "--port", "$WebPort"
    )
    $process = Start-Process -FilePath $python -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput (Join-Path $LogDirectory "web.out.log") `
        -RedirectStandardError (Join-Path $LogDirectory "web.err.log") `
        -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $WebPidPath -Value $process.Id -Encoding ASCII
    Write-Output "웹 화면을 준비하고 있습니다 (PID $($process.Id))."

    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (Test-WebReady) { Write-Output "AI 체력 코치 준비 완료: $WebUrl"; return }
        Start-Sleep -Seconds 2
    }
    throw "웹 서버가 준비되지 않았습니다. $LogDirectory\web.err.log를 확인해 주세요."
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $LogDirectory, $OutputDirectory | Out-Null

switch ($Action) {
    "start" {
        Sync-ChromaIndex
        Start-Model
        Start-Web
        if (-not $NoBrowser) { Start-Process $WebUrl }
    }
    "stop" {
        Stop-OwnedProcess $WebPidPath "python*" "웹 서버"
        Stop-OwnedProcess $ModelPidPath "llama-server*" "Qwen3 모델 서버"
    }
    "status" {
        Write-Output ("웹 서버: " + $(if (Test-WebReady) { "정상 ($WebUrl)" } else { "중지" }))
        Write-Output ("Qwen3: " + $(if (Test-ModelReady) { "정상 ($ModelUrl)" } else { "중지" }))
        Write-Output "실행 기록: $RuntimeRoot"
    }
}
