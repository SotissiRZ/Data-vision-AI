$ErrorActionPreference = "Stop"

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step a échoué (code $LASTEXITCODE). DataVision ne sera PAS démarré avec une ancienne image."
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$version = (Get-Content "$root/VERSION" -Raw).Trim()

& "$root/preflight-windows.ps1"
if (-not $?) { throw "Préflight échoué." }

& "$root/reset-docker.ps1"
if (-not $?) { throw "Nettoyage Docker échoué." }

Write-Host "Construction v$version (api + worker + web + sandbox)..." -ForegroundColor Yellow
docker compose build --no-cache api worker web sandbox
Assert-LastExit "docker compose build"

Write-Host "Validation des dépendances Python dans l’image API fraîchement construite..." -ForegroundColor Yellow
docker compose run --rm --no-deps api python -c "import fastapi,pydantic_settings,sqlalchemy,cryptography; from app.core.config import get_settings; s=get_settings(); print('Runtime Python OK - pydantic-settings disponible - DataVision', s.app_name)"
Assert-LastExit "runtime Python conteneurisé"

Write-Host "Démarrage de la stack..." -ForegroundColor Yellow
docker compose up -d
Assert-LastExit "docker compose up"

Write-Host "État des services:" -ForegroundColor Cyan
docker compose ps
Assert-LastExit "docker compose ps"

Write-Host "DataVision v$version a été construit et démarré sans réutiliser d'anciennes images." -ForegroundColor Green
Write-Host "UI:  http://localhost:3005" -ForegroundColor Green
Write-Host "API: http://localhost:8005/docs" -ForegroundColor Green
