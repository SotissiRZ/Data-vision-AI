$ErrorActionPreference = "Stop"
if (-not (Test-Path ".env")) {
  Write-Host "Aucun .env détecté : lancez d'abord .\install-windows.ps1" -ForegroundColor Yellow
  Copy-Item ".env.example" ".env"
}
docker compose up -d
Write-Host "DataVision démarré avec API + worker asynchrone." -ForegroundColor Green
Start-Process "http://localhost:3005"
