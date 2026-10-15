param([string]$GamePath)
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Resolve-GameFolder $GamePath
Assert-GameClosed $root
$statePath = Get-SafePath $root '.pstcontroller/state.json'
if (-not (Test-Path -LiteralPath $statePath)) { throw 'No installer-managed mod was found in this folder.' }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.status -eq 'uninstalled') { Write-Output 'Already uninstalled.'; exit 0 }
if ($state.status -ne 'installed') { throw 'Incomplete installation. Preserve .pstcontroller/backups for manual recovery.' }
Restore-ModFiles $root $state $true
$state.status = 'uninstalled'; Write-Utf8 $statePath ($state | ConvertTo-Json -Depth 8)
Write-Output 'Mod removed. Previous game files restored; backups and the separate save profile are preserved.'
