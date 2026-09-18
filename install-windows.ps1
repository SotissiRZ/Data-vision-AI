$ErrorActionPreference = "Stop"
Write-Host "DataVision AI v2.12 — installation locale" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker n'est pas disponible. Installez Docker Desktop puis relancez ce script."
}

docker version | Out-Null

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

# Ne jamais conserver les secrets d'exemple lors d'une installation locale neuve.
$envContent = Get-Content ".env" -Raw
$envChanged = $false
if ($envContent -match "AUTH_SECRET=change-") {
  $generatedSecret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
  $envContent = [regex]::Replace($envContent, "AUTH_SECRET=.*", "AUTH_SECRET=$generatedSecret")
  $envChanged = $true
  Write-Host "Secret d'authentification local généré." -ForegroundColor Green
}

if ($envContent -match "CONNECTOR_SECRET_KEY=change-") {
  $connectorSecret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
  $envContent = [regex]::Replace($envContent, "CONNECTOR_SECRET_KEY=.*", "CONNECTOR_SECRET_KEY=$connectorSecret")
  $envChanged = $true
  Write-Host "Clé de chiffrement des connecteurs générée." -ForegroundColor Green
}

if ($envChanged) {
  Set-Content ".env" $envContent -Encoding UTF8
}

Write-Host "Construction des images (cache BuildKit activé)..." -ForegroundColor Yellow
docker compose build

Write-Host "Démarrage de PostgreSQL, Redis, API, worker et interface..." -ForegroundColor Yellow
docker compose up -d

Write-Host "" 
Write-Host "DataVision: http://localhost:3005" -ForegroundColor Green
Write-Host "API:       http://localhost:8005" -ForegroundColor Green
Write-Host "OpenAPI:   http://localhost:8005/docs" -ForegroundColor Green
Write-Host "" 
Write-Host "Ouvrez Gouverner → Gouvernance pour initialiser le premier compte Enterprise." -ForegroundColor Cyan
Start-Process "http://localhost:3005"
