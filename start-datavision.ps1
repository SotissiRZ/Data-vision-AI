$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$version = (Get-Content "$root/VERSION" -Raw).Trim()

& "$root/preflight-windows.ps1"
if (-not $?) { throw "Préflight échoué." }
if (-not (Test-Path ".env")) { throw "Aucun .env détecté : lancez d'abord .\install-windows.ps1" }

python scripts/config_doctor.py --root . --env-file .env
if ($LASTEXITCODE -ne 0) { throw "Configuration invalide." }

docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up a échoué (code $LASTEXITCODE)." }
docker compose ps
Write-Host "DataVision v$version démarré." -ForegroundColor Green
Start-Process "http://localhost:3005"
