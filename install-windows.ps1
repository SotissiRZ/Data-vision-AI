$ErrorActionPreference = "Stop"
Write-Host "DataVision AI v1.0 — installation locale" -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker n'est pas disponible. Installez Docker Desktop puis relancez ce script."
}
docker version | Out-Null
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Write-Host "Construction des images (cache BuildKit activé)..." -ForegroundColor Yellow
docker compose build
Write-Host "Démarrage des services..." -ForegroundColor Yellow
docker compose up -d
Write-Host "DataVision: http://localhost:3005" -ForegroundColor Green
Write-Host "API:       http://localhost:8005" -ForegroundColor Green
Write-Host "OpenAPI:   http://localhost:8005/docs" -ForegroundColor Green
Start-Process "http://localhost:3005"
