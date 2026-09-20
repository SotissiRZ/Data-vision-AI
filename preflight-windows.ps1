$ErrorActionPreference = "Stop"

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step a échoué (code $LASTEXITCODE). Arrêt immédiat pour éviter l'utilisation d'anciennes images Docker."
  }
}

$expectedVersion = "2.42.0"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "DataVision AI — contrôle pré-build" -ForegroundColor Cyan

foreach ($required in @("VERSION", "backend/requirements.txt", "docker-compose.yml", "compliance/CDC_COVERAGE_MATRIX.json", "compliance/MVP_ACCEPTANCE.json", "compliance/PREPARATION_ACCEPTANCE.json", "frontend/next.config.mjs")) {
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
  throw "Ancienne dépendance cryptography==46.0.4 détectée. Ce dossier n'est pas une copie v2.42.0 valide."
}

Write-Host "VERSION: $version" -ForegroundColor Green
Write-Host "Dependency: $cryptoLine" -ForegroundColor Green

$composeText = Get-Content "docker-compose.yml" -Raw
if ($composeText -notmatch 'NEXT_PUBLIC_API_URL:\s*/api/backend') {
  throw "Proxy API same-origin absent du docker-compose.yml. Cette copie ne contient pas le baseline de production v2.42.0."
}
$dockerfileText = Get-Content "backend/Dockerfile" -Raw
if ($dockerfileText -notmatch 'COPY compliance ./compliance') {
  throw "Le Dockerfile backend n'embarque pas compliance/. Cette copie ne contient pas le baseline de production v2.42.0."
}
Write-Host "CDC assets/proxy: OK" -ForegroundColor Green

foreach ($requiredBaseline in @("frontend/lib/assistant/orchestrator-adapter.ts", "scripts/production_baseline.py", "scripts/mvp_acceptance.py", "scripts/preparation_acceptance.py", "scripts/verify_release.py", "backend/tests/test_mvp_workflow_v241.py", "backend/tests/test_data_preparation_v242.py", "backend/tests/test_pipelines_v242.py", "frontend/e2e/mvp.spec.ts")) {
  if (-not (Test-Path $requiredBaseline)) { throw "Baseline v2.42.0 incomplet: $requiredBaseline absent" }
}
python scripts/production_baseline.py --check
Assert-LastExit "production baseline"
Write-Host "Production baseline: OK" -ForegroundColor Green

python scripts/mvp_acceptance.py --root .
Assert-LastExit "MVP acceptance manifest"
Write-Host "MVP acceptance manifest: OK" -ForegroundColor Green

python scripts/preparation_acceptance.py --root .
Assert-LastExit "Data Preparation acceptance manifest"
Write-Host "Data Preparation acceptance manifest: OK" -ForegroundColor Green

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
