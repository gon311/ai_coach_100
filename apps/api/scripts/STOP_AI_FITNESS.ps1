$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$serverCandidates = Get-ChildItem -LiteralPath $packageRoot -Filter 'server.ps1' -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Directory.Name -eq 'tools' -and (Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'fitness_web_server.py')) }
if (@($serverCandidates).Count -ne 1) { throw 'AI Fitness server.ps1 must exist exactly once in this package.' }
$serverScript = $serverCandidates[0].FullName
$env:AI_FITNESS_RUNTIME_ROOT = Join-Path $packageRoot '.runtime_data'
& $serverScript -Action stop -WebPort 8501 -ModelPort 8089 -ContextSize 32768
exit $LASTEXITCODE
