$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "DataVision AI v2.39.0 — installation locale" -ForegroundColor Cyan
& "$root/preflight-windows.ps1"
if (-not $?) { throw "Préflight échoué." }

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

$envContent = Get-Content ".env" -Raw
$envChanged = $false
if ($envContent -match "AUTH_SECRET=change-") {
  $generatedSecret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
  $envContent = [regex]::Replace($envContent, "AUTH_SECRET=.*", "AUTH_SECRET=$generatedSecret")
  $envChanged = $true
}
if ($envContent -match "CONNECTOR_SECRET_KEY=change-") {
  $connectorSecret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
  $envContent = [regex]::Replace($envContent, "CONNECTOR_SECRET_KEY=.*", "CONNECTOR_SECRET_KEY=$connectorSecret")
  $envChanged = $true
}
if ($envChanged) { Set-Content ".env" $envContent -Encoding UTF8 }

& "$root/rebuild-windows.ps1"
