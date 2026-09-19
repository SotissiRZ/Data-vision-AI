$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

& "$root/preflight-windows.ps1"
if (-not $?) { throw "Préflight échoué." }
if (-not (Test-Path ".env")) { throw "Aucun .env détecté : lancez d'abord .\install-windows.ps1" }

docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up a échoué (code $LASTEXITCODE)." }
docker compose ps
Write-Host "DataVision v2.39.0 démarré." -ForegroundColor Green
Start-Process "http://localhost:3005"
