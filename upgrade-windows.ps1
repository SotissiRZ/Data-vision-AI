param(
  [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$version = (Get-Content "$root/VERSION" -Raw).Trim()

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step a échoué (code $LASTEXITCODE)." }
}

Write-Host "DataVision AI v$version — upgrade contrôlé" -ForegroundColor Cyan
& "$root/preflight-windows.ps1"
if (-not $?) { throw "Préflight échoué." }
if (-not (Test-Path ".env")) { throw "Aucun .env existant. Utilisez install-windows.ps1 pour une nouvelle installation." }

python scripts/config_doctor.py --root . --env-file .env
Assert-LastExit "config doctor"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $root "upgrade-backups/$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item ".env" (Join-Path $backupDir ".env")
Copy-Item "VERSION" (Join-Path $backupDir "VERSION.target")

if (-not $SkipBackup) {
  Write-Host "Création d'une sauvegarde applicative avant migration..." -ForegroundColor Yellow
  docker compose up -d postgres redis
  Assert-LastExit "démarrage des dépendances"
  docker compose --profile ops run --rm backup
  Assert-LastExit "backup pré-upgrade"
}

Write-Host "Construction des images v$version..." -ForegroundColor Yellow
docker compose build api worker web sandbox
Assert-LastExit "docker compose build"

Write-Host "Application des migrations explicites..." -ForegroundColor Yellow
docker compose --profile ops run --rm migrate
Assert-LastExit "schema migrate"

Write-Host "Démarrage de DataVision v$version..." -ForegroundColor Yellow
docker compose up -d
Assert-LastExit "docker compose up"

$ready = $false
1..60 | ForEach-Object {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8005/health/ready" -TimeoutSec 5
    if ($response.StatusCode -eq 200) { $ready = $true; return }
  } catch { Start-Sleep -Seconds 3 }
}
if (-not $ready) { throw "Upgrade terminé mais readiness API non atteinte. Consultez docker compose logs api worker web." }

Write-Host "Upgrade vers DataVision v$version validé. Les volumes Docker ont été conservés." -ForegroundColor Green
Write-Host "Sauvegarde locale de configuration: $backupDir" -ForegroundColor DarkCyan
