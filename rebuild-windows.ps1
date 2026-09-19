$ErrorActionPreference = "Stop"

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step a échoué (code $LASTEXITCODE). DataVision ne sera PAS démarré avec une ancienne image."
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

& "$root/preflight-windows.ps1"
if (-not $?) { throw "Préflight échoué." }

& "$root/reset-docker.ps1"
if (-not $?) { throw "Nettoyage Docker échoué." }

Write-Host "Construction v2.39.0 (api + worker + web)..." -ForegroundColor Yellow
docker compose build --no-cache api worker web
Assert-LastExit "docker compose build"

Write-Host "Démarrage de la stack..." -ForegroundColor Yellow
docker compose up -d
Assert-LastExit "docker compose up"

Write-Host "État des services:" -ForegroundColor Cyan
docker compose ps
Assert-LastExit "docker compose ps"

Write-Host "DataVision v2.39.0 a été construit et démarré sans réutiliser d'anciennes images." -ForegroundColor Green
Write-Host "UI:  http://localhost:3005" -ForegroundColor Green
Write-Host "API: http://localhost:8005/docs" -ForegroundColor Green
