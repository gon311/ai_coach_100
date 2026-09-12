$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$venvPython = Join-Path $packageRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = Get-Command python.exe -ErrorAction Stop
    & $pythonCommand.Source -m venv (Join-Path $packageRoot '.venv')
}
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $packageRoot 'AI_체력_코치_Qwen3_4B_Q4_배포\requirements.txt')
Write-Host '설치 완료. START_AI_FITNESS.ps1을 실행하세요.'
