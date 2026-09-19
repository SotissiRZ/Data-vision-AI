$ErrorActionPreference = "Stop"

function Assert-LastExit([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step a échoué (code $LASTEXITCODE)." }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Nettoyage Docker DataVision (volumes conservés)..." -ForegroundColor Yellow

docker compose down --remove-orphans
if ($LASTEXITCODE -ne 0) {
  Write-Host "docker compose down n'a pas terminé proprement; nettoyage ciblé..." -ForegroundColor Yellow
}

$knownContainers = @(
  "datavision-api-1", "datavision-worker-1", "datavision-web-1",
  "datavision-postgres-1", "datavision-redis-1", "datavision-sandbox-1", "datavision-clamav-1"
)
$existing = @(docker ps -a --format "{{.Names}}")
foreach ($name in $knownContainers) {
  if ($existing -contains $name) {
    Write-Host "Suppression du conteneur orphelin $name" -ForegroundColor DarkYellow
    docker rm -f $name | Out-Null
  }
}

$knownNetworks = @("datavision_default", "datavision_notebook_sandbox")
$networks = @(docker network ls --format "{{.Name}}")
foreach ($network in $knownNetworks) {
  if ($networks -contains $network) {
    docker network rm $network 2>$null | Out-Null
  }
}

# Supprime les anciennes images applicatives afin qu'un build échoué ne puisse pas
# relancer silencieusement une version antérieure. Les images de données et les volumes
# PostgreSQL/Redis/ClamAV restent conservés : postgres_data, redis_data, clamav_data.
$projectImages = @("datavision-api", "datavision-worker", "datavision-web")
$images = @(docker image ls --format "{{.Repository}}")
foreach ($image in $projectImages) {
  if ($images -contains $image) {
    Write-Host "Suppression de l'ancienne image $image" -ForegroundColor DarkYellow
    docker image rm -f $image | Out-Null
  }
}

Write-Host "Nettoyage terminé. Les volumes de données n'ont pas été supprimés." -ForegroundColor Green
