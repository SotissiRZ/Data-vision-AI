param(
  [string]$EvidenceDir = "production-evidence",
  [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Record-Evidence([string]$Kind, [string]$Status, [string]$Source, [string]$Details, [string]$Attachment = "") {
  $args = @("scripts/production_signoff.py", "record", "--evidence-dir", $EvidenceDir, "--kind", $Kind, "--status", $Status, "--source", $Source, "--actor", $env:USERNAME, "--details", $Details)
  if ($Attachment) { $args += @("--attachment", $Attachment) }
  python @args
}

python scripts/production_acceptance.py --root . --check
Copy-Item .env.example .env -ErrorAction SilentlyContinue

docker compose config -q
Record-Evidence "compose" "pass" "local-windows" "docker compose config -q passed"

docker compose up -d --build postgres redis sandbox api worker web
try {
  $ready = $false
  1..90 | ForEach-Object {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:3005/api/health" -TimeoutSec 5
      if ($response.StatusCode -eq 200) { $ready = $true; return }
    } catch { Start-Sleep -Seconds 3 }
  }
  if (-not $ready) { throw "DataVision web readiness timed out" }

  Push-Location frontend
  npm install
  npm run typecheck
  npm run build
  if (-not $SkipBrowserInstall) { npx playwright install chromium }
  npm run test:e2e:smoke
  npm run test:e2e:mvp
  npm run test:e2e:production
  Pop-Location
  Record-Evidence "e2e" "pass" "local-windows" "Playwright smoke, MVP and production suites passed"

  python scripts/load_smoke.py --url http://127.0.0.1:3005/api/health --requests 80 --concurrency 8 --json-out "$EvidenceDir/production-load.json"
  Record-Evidence "load" "pass" "local-windows" "HTTP load smoke passed" "$EvidenceDir/production-load.json"
} finally {
  docker compose ps | Out-File -Encoding utf8 "$EvidenceDir/compose-ps.txt"
  docker compose down
}

Write-Host "Local Docker/E2E/load evidence recorded. CI, Helm, security and UAT evidence must be recorded from their authoritative environments."
python scripts/production_signoff.py verify --evidence-dir $EvidenceDir
