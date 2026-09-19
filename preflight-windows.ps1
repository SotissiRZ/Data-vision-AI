$ErrorActionPreference = "Stop"

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step a échoué (code $LASTEXITCODE). Arrêt immédiat pour éviter l'utilisation d'anciennes images Docker."
  }
}

$expectedVersion = "2.39.0"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "DataVision AI — contrôle pré-build" -ForegroundColor Cyan

foreach ($required in @("VERSION", "backend/requirements.txt", "docker-compose.yml")) {
  if (-not (Test-Path $required)) { throw "Fichier requis absent: $required" }
}

$version = (Get-Content "VERSION" -Raw).Trim()
if ($version -ne $expectedVersion) {
  throw "Mauvais dossier DataVision. VERSION=$version, attendu=$expectedVersion. Vous êtes probablement encore dans une ancienne copie du projet."
}

$requirements = Get-Content "backend/requirements.txt"
$cryptoLine = $requirements | Where-Object { $_ -match '^cryptography' } | Select-Object -First 1
if ($cryptoLine -ne "cryptography==46.0.5") {
  throw "Dépendance cryptography incorrecte: '$cryptoLine'. Attendu: cryptography==46.0.5. N'exécutez pas Docker depuis ce dossier."
}
if ($requirements -contains "cryptography==46.0.4") {
  throw "Ancienne dépendance cryptography==46.0.4 détectée. Ce dossier n'est pas une copie v2.39.0 valide."
}

Write-Host "VERSION: $version" -ForegroundColor Green
Write-Host "Dependency: $cryptoLine" -ForegroundColor Green

python scripts/repository_hygiene.py --check
Assert-LastExit "repository hygiene"
Write-Host "requirements SHA256:" -ForegroundColor DarkCyan
(Get-FileHash "backend/requirements.txt" -Algorithm SHA256).Hash | Write-Host

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker n'est pas disponible. Installez/démarrez Docker Desktop."
}

docker version | Out-Null
Assert-LastExit "docker version"

docker compose version | Out-Null
Assert-LastExit "docker compose version"

docker compose config --quiet
Assert-LastExit "docker compose config"

Write-Host "Préflight OK. Le dossier courant est bien DataVision v$expectedVersion." -ForegroundColor Green
