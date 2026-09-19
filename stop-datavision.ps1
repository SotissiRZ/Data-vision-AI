$ErrorActionPreference = "Stop"
Write-Host "Arrêt de DataVision..." -ForegroundColor Yellow
docker compose down --remove-orphans
Write-Host "DataVision arrêté. Les volumes de données sont conservés." -ForegroundColor Green
