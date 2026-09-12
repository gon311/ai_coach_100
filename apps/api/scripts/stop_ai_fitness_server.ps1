$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "server.ps1") -Action stop
exit $LASTEXITCODE
