$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$serverCandidates = Get-ChildItem -LiteralPath $packageRoot -Filter 'server.ps1' -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Directory.Name -eq 'tools' -and (Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'fitness_web_server.py')) }
if (@($serverCandidates).Count -ne 1) { throw 'AI Fitness server.ps1 must exist exactly once in this package.' }
$serverScript = $serverCandidates[0].FullName
$deployment = Split-Path -Parent $serverCandidates[0].Directory.FullName
$frontendFile = Join-Path $packageRoot 'frontend1\fit-coach-webview.html'
$runtimeRoot = Join-Path $packageRoot '.runtime_data'

$pythonCandidates = @(
    (Join-Path $packageRoot '.venv\Scripts\python.exe'),
    'E:\EyeGuideRAG\.venv\Scripts\python.exe'
)
$pythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $pythonExe) {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $pythonExe = $command.Source }
}
if (-not $pythonExe) { throw 'Python was not found. Run SETUP_IF_NEEDED.ps1 first.' }

foreach ($required in @($serverScript,$frontendFile,(Join-Path $deployment 'models\Qwen3-4B-Q4_K_M.gguf'),(Join-Path $deployment 'artifacts\rag_documents.sqlite'))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required file not found: $required" }
}

$env:AI_FITNESS_FRONTEND_FILE = $frontendFile
$env:AI_FITNESS_CONTEXT_SIZE = '32768'
$env:AI_FITNESS_MAX_TOKENS = '8192'
$env:AI_FITNESS_PYTHON = $pythonExe
$env:AI_FITNESS_RUNTIME_ROOT = $runtimeRoot

& $serverScript -Action start -WebPort 8501 -ModelPort 8089 -ContextSize 32768
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Open: http://127.0.0.1:8501'
