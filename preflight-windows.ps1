$ErrorActionPreference = "Stop"

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step a échoué (code $LASTEXITCODE). Arrêt immédiat pour éviter l'utilisation d'anciennes images Docker."
  }
}

$expectedVersion = "2.53.0"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "DataVision AI — contrôle pré-build" -ForegroundColor Cyan

foreach ($required in @("VERSION", "backend/requirements.txt", "docker-compose.yml", "compliance/CDC_COVERAGE_MATRIX.json", "compliance/MVP_ACCEPTANCE.json", "compliance/PREPARATION_ACCEPTANCE.json", "compliance/WORKSPACE_ACCEPTANCE.json", "compliance/ASSISTANT_ACCEPTANCE.json", "compliance/ASSISTANT_MULTIMODAL_ACCEPTANCE.json", "compliance/INSIGHT_ACCEPTANCE.json", "compliance/REPORT_ACCEPTANCE.json", "compliance/AUTOML_ACCEPTANCE.json", "compliance/ML_SAFETY_ACCEPTANCE.json", "compliance/FORECASTING_ANOMALY_ACCEPTANCE.json", "frontend/next.config.mjs")) {
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
  throw "Ancienne dépendance cryptography==46.0.4 détectée. Ce dossier n'est pas une copie v2.53.0 valide."
}

Write-Host "VERSION: $version" -ForegroundColor Green
Write-Host "Dependency: $cryptoLine" -ForegroundColor Green

$composeText = Get-Content "docker-compose.yml" -Raw
if ($composeText -notmatch 'NEXT_PUBLIC_API_URL:\s*/api/backend') {
  throw "Proxy API same-origin absent du docker-compose.yml. Cette copie ne contient pas le baseline de production v2.53.0."
}
$dockerfileText = Get-Content "backend/Dockerfile" -Raw
if ($dockerfileText -notmatch 'COPY compliance ./compliance') {
  throw "Le Dockerfile backend n'embarque pas compliance/. Cette copie ne contient pas le baseline de production v2.53.0."
}
Write-Host "CDC assets/proxy: OK" -ForegroundColor Green

foreach ($requiredBaseline in @("frontend/lib/assistant/orchestrator-adapter.ts", "scripts/production_baseline.py", "scripts/mvp_acceptance.py", "scripts/preparation_acceptance.py", "scripts/workspace_acceptance.py", "scripts/assistant_acceptance.py", "scripts/assistant_multimodal_acceptance.py", "scripts/multi_agent_acceptance.py", "scripts/semantic_acceptance.py", "scripts/insight_acceptance.py", "scripts/report_acceptance.py", "scripts/automl_acceptance.py", "scripts/ml_safety_acceptance.py", "scripts/xai_acceptance.py", "scripts/forecasting_anomaly_acceptance.py", "scripts/verify_release.py", "backend/tests/test_mvp_workflow_v241.py", "backend/tests/test_data_preparation_v242.py", "backend/tests/test_pipelines_v242.py", "backend/tests/test_data_workspace_v243.py", "backend/tests/test_frontend_workspace_v243.py", "backend/tests/assistant/test_assistant_v244.py", "backend/tests/test_frontend_assistant_v244.py", "backend/tests/assistant/test_assistant_v245.py", "backend/tests/test_frontend_assistant_v245.py", "backend/tests/assistant/test_multi_agent_v246.py", "backend/tests/test_frontend_assistant_v246.py", "backend/tests/test_semantic_nlq_v247.py", "backend/tests/test_frontend_semantic_v247.py", "backend/tests/test_insight_engine_v248.py", "backend/tests/test_frontend_insights_v248.py", "backend/tests/test_reporting_v249.py", "backend/tests/test_frontend_reporting_v249.py", "backend/tests/test_automl_v2500.py", "backend/tests/test_frontend_automl_v2500.py", "backend/tests/test_ml_safety_v2510.py", "backend/tests/test_xai_v2520.py", "backend/tests/test_forecasting_anomaly_v2530.py", "backend/app/services/ml_guardrails.py", "backend/app/services/insight_engine.py", "backend/app/assistant/agents.py", "frontend/lib/assistant/effects.ts", "frontend/e2e/mvp.spec.ts")) {
  if (-not (Test-Path $requiredBaseline)) { throw "Baseline v2.53.0 incomplet: $requiredBaseline absent" }
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

python scripts/workspace_acceptance.py --root .
Assert-LastExit "Data Workspace acceptance manifest"
Write-Host "Data Workspace acceptance manifest: OK" -ForegroundColor Green

python scripts/assistant_acceptance.py --root .
Assert-LastExit "Assistant V1 acceptance manifest"
Write-Host "Assistant V1 acceptance manifest: OK" -ForegroundColor Green

python scripts/assistant_multimodal_acceptance.py --root . --check
Assert-LastExit "Assistant multimodal acceptance manifest"
Write-Host "Assistant multimodal acceptance manifest: OK" -ForegroundColor Green

python scripts/multi_agent_acceptance.py --root . --check
Assert-LastExit "Multi-agent acceptance manifest"
Write-Host "Multi-agent acceptance manifest: OK" -ForegroundColor Green

python scripts/semantic_acceptance.py --root . --check
Assert-LastExit "Semantic/NLQ acceptance manifest"
Write-Host "Semantic/NLQ acceptance manifest: OK" -ForegroundColor Green

python scripts/insight_acceptance.py --root . --check
Assert-LastExit "Insight Engine acceptance manifest"
Write-Host "Insight Engine acceptance manifest: OK" -ForegroundColor Green

python scripts/report_acceptance.py --root . --check
Assert-LastExit "Report Builder acceptance manifest"
Write-Host "Report Builder acceptance manifest: OK" -ForegroundColor Green

python scripts/automl_acceptance.py --root . --check
Assert-LastExit "AutoML acceptance manifest"
Write-Host "AutoML acceptance manifest: OK" -ForegroundColor Green

python scripts/ml_safety_acceptance.py --root . --check
Assert-LastExit "ML Safety acceptance manifest"
Write-Host "ML Safety acceptance manifest: OK" -ForegroundColor Green

python scripts/xai_acceptance.py --root . --check
Assert-LastExit "XAI acceptance manifest"
Write-Host "XAI acceptance manifest: OK" -ForegroundColor Green

python scripts/forecasting_anomaly_acceptance.py --root . --check
Assert-LastExit "Forecasting/Anomaly acceptance manifest"
Write-Host "Forecasting/Anomaly acceptance manifest: OK" -ForegroundColor Green

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
