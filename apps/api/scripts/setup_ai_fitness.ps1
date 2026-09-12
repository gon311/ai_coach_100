$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = if ($env:AI_FITNESS_RUNTIME_ROOT) {
    $env:AI_FITNESS_RUNTIME_ROOT
} else {
    "C:\ai_fitness_qwen3_runtime"
}
$VirtualEnvironment = Join-Path $RuntimeRoot "venv"
$VirtualPython = Join-Path $VirtualEnvironment "Scripts\python.exe"

function Find-BasePython {
    if ($env:AI_FITNESS_BASE_PYTHON -and (Test-Path -LiteralPath $env:AI_FITNESS_BASE_PYTHON -PathType Leaf)) {
        return $env:AI_FITNESS_BASE_PYTHON
    }
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    $pythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) { return $pythonCommand.Source }
    throw "Python 3.12를 찾을 수 없습니다. Python 3.12 설치 후 다시 실행해 주세요."
}

$basePython = Find-BasePython
$versionText = (& $basePython -c "import sys; print('.'.join(map(str, sys.version_info[:2])))").Trim()
if ($LASTEXITCODE -ne 0 -or [version]$versionText -lt [version]"3.10") {
    throw "Python 3.10 이상이 필요합니다. 현재 버전: $versionText"
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
if (-not (Test-Path -LiteralPath $VirtualPython -PathType Leaf)) {
    Write-Output "AI 체력 코치 전용 Python 환경을 만듭니다."
    & $basePython -m venv $VirtualEnvironment
    if ($LASTEXITCODE -ne 0) { throw "전용 Python 환경 생성에 실패했습니다." }
}

Write-Output "필수 Python 패키지를 설치합니다. 처음 한 번은 인터넷 연결이 필요합니다."
& $VirtualPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip 업데이트에 실패했습니다." }
& $VirtualPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "필수 패키지 설치에 실패했습니다." }

& $VirtualPython -c "import fastapi,uvicorn,chromadb,sentence_transformers,pydantic; print('Python package check: OK')"
if ($LASTEXITCODE -ne 0) { throw "설치 후 패키지 확인에 실패했습니다." }

$requiredFiles = @(
    (Join-Path $ProjectRoot "models\Qwen3-4B-Q4_K_M.gguf"),
    (Join-Path $ProjectRoot "models\ko-sroberta-multitask\model.safetensors"),
    (Join-Path $ProjectRoot "runtime\llama\llama-server.exe"),
    (Join-Path $ProjectRoot "artifacts\rag_documents.sqlite"),
    (Join-Path $ProjectRoot "artifacts\chroma\BUILD_COMPLETE.json"),
    (Join-Path $ProjectRoot "artifacts\center_percentile_norms.sqlite"),
    (Join-Path $ProjectRoot "artifacts\age_bmi_recommendation_rules.sqlite"),
    (Join-Path $ProjectRoot "artifacts\korean_adult_bmi_standards.json"),
    (Join-Path $ProjectRoot "source_data\KS_MRFN_AGE_ACCTO_RECOMMEND_SPORTS_INFO_202607.csv"),
    (Join-Path $ProjectRoot "source_data\국민연령별추천운동정보_컬럼정의서.xls")
)
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "배포 필수 파일이 없습니다: $requiredFile"
    }
}

Write-Output "설치 및 배포 파일 확인 완료"
Write-Output "이제 START_AI_FITNESS_SERVER.cmd를 더블클릭하세요."
