$ErrorActionPreference = "Stop"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
docker compose up -d
Start-Process "http://localhost:3005"
