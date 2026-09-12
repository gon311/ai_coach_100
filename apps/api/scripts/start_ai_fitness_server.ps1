param(
    [int]$WebPort = 8501,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "server.ps1") -Action start -WebPort $WebPort -NoBrowser:$NoBrowser
exit $LASTEXITCODE
