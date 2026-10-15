param([string]$GamePath, [switch]$ImportSaves, [switch]$SkipSaveImport, [string]$SourceProfile)
$interactiveInstall = [string]::IsNullOrWhiteSpace($GamePath)
if ($ImportSaves -and $SkipSaveImport) { throw 'Choose ImportSaves or SkipSaveImport, not both.' }
$manifestPath = Join-Path $PSScriptRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'payload') -PathType Container)) {
    throw 'This is a source package or an incomplete extraction. Extract the complete PSTEE-Xbox-Controller-v*-preview.zip and run Install.cmd from its root folder. Do not run distribution/Install.cmd from the source package. No game files changed.'
}
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Resolve-GameFolder $GamePath
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$exe = Get-SafePath $root 'Torment.exe'
if (-not (Test-Path -LiteralPath $exe) -or (Get-PathHash $exe) -ne $manifest.exeSha256) {
    throw 'Unsupported executable. This preview supports the verified Windows x64 3.2.2.0 fingerprint only.'
}
Assert-GameClosed $root
$statePath = Get-SafePath $root '.pstcontroller/state.json'
if (Test-Path -LiteralPath $statePath) {
    $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($previous.status -notin @('uninstalled','rolled-back')) { throw 'A mod installation is already present. Uninstall it before installing this release.' }
} elseif (Test-Path -LiteralPath (Get-SafePath $root '.pstcontroller')) {
    throw 'An unknown .pstcontroller folder exists. Preserve it and choose a clean game copy.'
}

# Validate all package files, stock resources and conflicts before any mutation.
foreach ($file in $manifest.payload) {
    $path = Get-SafePath $PSScriptRoot $file.path
    if ((Get-PathHash $path) -ne $file.sha256) { throw "Package checksum failed: $($file.path)" }
}
$patch = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'payload/ui-patch.json') -Raw | ConvertFrom-Json
$ui = Apply-UiPatch (Read-GameUI $root) $patch
$existingUi = Get-SafePath $root 'override/UI.menu'
if (Test-Path -LiteralPath $existingUi) {
    $text = [IO.File]::ReadAllText($existingUi,$script:Utf8).TrimStart([char]0xfeff).Replace("`r`n","`n").Replace("`r","`n")
    if ((Get-ByteHash ($script:Utf8.GetBytes($text))) -ne $patch.sourceSha256) {
        throw 'A custom UI.menu is installed. This preview cannot merge other UI mods; choose a clean game copy.'
    }
}
foreach ($relative in @('ControllerLab.exe','override/M_PSTPAD.lua','override/pstcontroller.dll','Play-Controller-Mod.cmd','override/PSTPRAD.bam','override/PSTPSEL.bam')) {
    if (Test-Path -LiteralPath (Get-SafePath $root $relative)) { throw "An existing mod file would be replaced: $relative. Use a clean copy or uninstall first." }
}
$enginePath = Get-SafePath $root 'engine.lua'
$engine = [IO.File]::ReadAllText($enginePath,$script:Utf8)
$pattern = '(?m)^[ \t]*engine_name[ \t]*=[^\r\n]*'
if ([regex]::Matches($engine,$pattern).Count -ne 1) { throw 'Unexpected engine.lua. No files changed.' }
$engine = [regex]::Replace($engine,$pattern,'engine_name="Planescape Torment - Controller Lab"')
$launch = "@echo off`r`npushd `"%~dp0`"`r`nstart `"`" `"ControllerLab.exe`"`r`npopd`r`n"
$data = @{
    'engine.lua' = $script:Utf8.GetBytes($engine)
    'ControllerLab.exe' = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'payload/ControllerLab.exe'))
    'override/M_PSTPAD.lua' = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'payload/M_PSTPAD.lua'))
    'override/pstcontroller.dll' = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'payload/pstcontroller.dll'))
    'override/UI.menu' = $ui
    'override/PSTPRAD.bam' = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'payload/PSTPRAD.bam'))
    'override/PSTPSEL.bam' = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'payload/PSTPSEL.bam'))
    'Play-Controller-Mod.cmd' = $script:Utf8.GetBytes($launch)
}
$backupSet = [Guid]::NewGuid().ToString('N')
$backupRoot = Get-SafePath $root ('.pstcontroller/backups/'+$backupSet)
$stageRoot = Get-SafePath $root ('.pstcontroller/stage/'+$backupSet)
$state = @{version=$manifest.version; status='installing'; backupSet=$backupSet; files=@()}
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
$override = Get-SafePath $root 'override'
New-Item -ItemType Directory -Path $override -Force | Out-Null
try {
    for ($index=0; $index -lt $script:ModFiles.Count; $index++) {
        $relative = $script:ModFiles[$index]; $target = Get-SafePath $root $relative
        $backup = '{0:d2}.bin' -f $index; $exists = Test-Path -LiteralPath $target
        $originalHash = $null
        if ($exists) {
            $originalHash = Get-PathHash $target
            [IO.File]::Copy($target,(Join-Path $backupRoot $backup),$false)
            if ((Get-PathHash (Join-Path $backupRoot $backup)) -ne $originalHash) { throw 'Backup verification failed.' }
        }
        $state.files += @{path=$relative; backup=$backup; existed=$exists; originalHash=$originalHash; installedHash=(Get-ByteHash $data[$relative])}
        [IO.File]::WriteAllBytes((Join-Path $stageRoot $backup),$data[$relative])
    }
    Write-Utf8 $statePath ($state | ConvertTo-Json -Depth 8)
    for ($index=0; $index -lt $state.files.Count; $index++) {
        $entry = $state.files[$index]; $target = Get-SafePath $root $entry.path
        $stage = Join-Path $stageRoot $entry.backup
        if (Test-Path -LiteralPath $target) { [IO.File]::Replace($stage,$target,[System.Management.Automation.Language.NullString]::Value) }
        else { [IO.File]::Move($stage,$target) }
    }
    $state.status = 'installed'; Write-Utf8 $statePath ($state | ConvertTo-Json -Depth 8)
} catch {
    $failure = $_
    Restore-ModFiles $root $state $false
    $state.status = 'rolled-back'; Write-Utf8 $statePath ($state | ConvertTo-Json -Depth 8)
    throw $failure
}
Write-Output "Installed PST:EE Xbox Controller Mod $($manifest.version) in $root"
Write-Output 'Start Play-Controller-Mod.cmd or ControllerLab.exe in that folder.'
Write-Output 'Saves/settings use the separate Documents/Planescape Torment - Controller Lab profile.'
Write-Output 'For Steam, set this game to Disable Steam Input.'
$copySaves = $ImportSaves.IsPresent
if ($interactiveInstall -and -not $SkipSaveImport -and -not $copySaves) {
    $originalProfile = $SourceProfile
    if (-not $originalProfile) { $originalProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Planescape Torment - Enhanced Edition' }
    if (Test-Path -LiteralPath (Join-Path $originalProfile 'save') -PathType Container) {
        Add-Type -AssemblyName System.Windows.Forms
        $answer = [Windows.Forms.MessageBox]::Show('Copy your existing local saves into the Controller Lab profile? Originals and existing target saves will be kept. This can also be done later with Import-Saves.cmd.',
            'Import existing saves', [Windows.Forms.MessageBoxButtons]::YesNo, [Windows.Forms.MessageBoxIcon]::Question)
        $copySaves = $answer -eq [Windows.Forms.DialogResult]::Yes
    }
}
if ($copySaves) {
    try { & (Join-Path $PSScriptRoot 'Import-Saves.ps1') -SourceProfile $SourceProfile }
    catch { Write-Warning "The mod is installed, but save import did not complete: $_. Close the game and run Import-Saves.cmd to retry." }
} else { Write-Output 'To copy existing saves later, close the game and run Import-Saves.cmd from this preview folder.' }
