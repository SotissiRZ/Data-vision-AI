param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
$archive = Join-Path $Root 'docs\history\legacy-root'
$migrations = Join-Path $Root 'docs\history\migrations'
$manifests = Join-Path $Root 'docs\history\manifests'
New-Item -ItemType Directory -Force -Path $archive,$migrations,$manifests | Out-Null

$items = @(
  @{ Name='manifest.json'; Destination=(Join-Path $manifests 'legacy-root-manifest.json') },
  @{ Name='pytest.ini'; Destination=(Join-Path $archive 'pytest.ini') },
  @{ Name='start.bat'; Destination=(Join-Path $archive 'start.bat') },
  @{ Name='MIGRATION_FROM_V212.md'; Destination=(Join-Path $migrations 'MIGRATION_FROM_V212.md') },
  @{ Name='MIGRATION_GUIDE.md'; Destination=(Join-Path $migrations 'MIGRATION_GUIDE_LEGACY.md') },
  @{ Name='CDC_DataVision_AI.md'; Destination=(Join-Path $archive 'CDC_DataVision_AI.md') }
)

foreach ($item in $items) {
  $source = Join-Path $Root $item.Name
  if (-not (Test-Path $source -PathType Leaf)) { continue }
  $destination = $item.Destination
  if (Test-Path $destination) {
    $hashA = (Get-FileHash -Algorithm SHA256 $source).Hash
    $hashB = (Get-FileHash -Algorithm SHA256 $destination).Hash
    if ($hashA -eq $hashB) {
      Remove-Item -Force $source
      Write-Host "Removed duplicate legacy root file: $($item.Name)"
      continue
    }
    $destination = "$destination.root-legacy"
  }
  Move-Item -Force $source $destination
  Write-Host "Archived legacy root file: $($item.Name) -> $destination"
}

python (Join-Path $Root 'scripts\repository_hygiene.py') --root $Root --check
