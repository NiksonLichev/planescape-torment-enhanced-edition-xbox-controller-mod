param([string]$SourceProfile, [string]$DestinationProfile)
. (Join-Path $PSScriptRoot 'Common.ps1')

$documents = [Environment]::GetFolderPath('MyDocuments')
if (-not $SourceProfile) { $SourceProfile = Join-Path $documents 'Planescape Torment - Enhanced Edition' }
if (-not $DestinationProfile) { $DestinationProfile = Join-Path $documents 'Planescape Torment - Controller Lab' }
$source = [IO.Path]::GetFullPath($SourceProfile).TrimEnd('\','/')
$destination = [IO.Path]::GetFullPath($DestinationProfile).TrimEnd('\','/')
if ($source -eq $destination -or $source.StartsWith($destination+'\',[StringComparison]::OrdinalIgnoreCase) -or
    $destination.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Source and destination must be separate, non-nested profile folders.'
}
if (@(Get-Process -Name Torment -ErrorAction SilentlyContinue).Count) {
    throw 'Close Planescape Torment before copying saves. No saves changed.'
}
$sourceSave = Get-SafePath $source 'save'
$targetSave = Get-SafePath $destination 'save'
if (-not (Test-Path -LiteralPath $sourceSave -PathType Container)) {
    throw "No local save folder found in $source. Use -SourceProfile to select your original profile."
}

function Get-SaveSnapshot([string]$Folder) {
    $entries = @()
    foreach ($item in @(Get-ChildItem -LiteralPath $Folder -Recurse -Force | Sort-Object FullName)) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked save files/folders are not supported.' }
        if (-not $item.PSIsContainer) {
            $relative = $item.FullName.Substring($Folder.Length+1)
            $entries += [pscustomobject]@{path=$relative; hash=(Get-PathHash $item.FullName)}
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'BALDUR.gam') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $Folder 'BALDUR.SAV') -PathType Leaf)) { return $null }
    $signature = ($entries | ForEach-Object { $_.path.ToLowerInvariant()+'='+$_.hash }) -join "`n"
    return [pscustomobject]@{entries=$entries; signature=$signature}
}

# Plan and validate every source slot before creating anything in the target.
$sources = @()
foreach ($slot in @(Get-ChildItem -LiteralPath $sourceSave -Directory -Force | Sort-Object Name)) {
    if ($slot.Name -notmatch '^\d{9}-.+') { continue }
    $slotPath = Get-SafePath $sourceSave $slot.Name
    $snapshot = Get-SaveSnapshot $slotPath
    if ($null -ne $snapshot) { $sources += [pscustomobject]@{folder=$slot; snapshot=$snapshot} }
}
if (-not $sources.Count) { Write-Output 'No complete local saves found. Nothing copied.'; return }
$known = @{}
$nextSlot = 2
if (Test-Path -LiteralPath $targetSave -PathType Container) {
    foreach ($slot in @(Get-ChildItem -LiteralPath $targetSave -Directory -Force)) {
        if ($slot.Name -notmatch '^(\d{9})-.+') { continue }
        $nextSlot = [Math]::Max($nextSlot, [long]$Matches[1]+1)
        $slotPath = Get-SafePath $targetSave $slot.Name
        $snapshot = Get-SaveSnapshot $slotPath
        if ($null -ne $snapshot) { $known[$snapshot.signature] = $true }
    }
}
New-Item -ItemType Directory -Path $targetSave -Force | Out-Null
$copied = 0; $skipped = 0
foreach ($save in $sources) {
    if ($known.ContainsKey($save.snapshot.signature)) { $skipped++; continue }
    $name = $save.folder.Name
    $target = Get-SafePath $targetSave $name
    if (Test-Path -LiteralPath $target) {
        $suffix = $name.Substring(10)
        do {
            if ($nextSlot -gt 999999999) { throw 'No free save slot number remains.' }
            $name = ('{0:d9}-{1}' -f [long]$nextSlot,$suffix); $nextSlot++
            $target = Get-SafePath $targetSave $name
        } while (Test-Path -LiteralPath $target)
    }
    # Publish complete verified slots atomically; never merge/overwrite a slot.
    $stage = Get-SafePath $targetSave ('.pstcontroller-import-'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    try {
        foreach ($entry in $save.snapshot.entries) {
            $from = Get-SafePath $save.folder.FullName $entry.path
            $to = Get-SafePath $stage $entry.path
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to)) | Out-Null
            [IO.File]::Copy($from,$to,$false)
            if ((Get-PathHash $to) -ne $entry.hash -or (Get-PathHash $from) -ne $entry.hash) {
                throw 'A source save changed or failed verification. The incomplete copy was not published.'
            }
        }
        [IO.Directory]::Move($stage,$target)
        $known[$save.snapshot.signature] = $true
        $copied++
    } finally {
        if (Test-Path -LiteralPath $stage) {
            $checkedStage = Get-SafePath $targetSave ([IO.Path]::GetFileName($stage))
            if ($checkedStage -ne $stage -or -not $checkedStage.StartsWith($targetSave+'\.pstcontroller-import-',[StringComparison]::OrdinalIgnoreCase)) {
                throw 'Refused cleanup outside the save import staging folder.'
            }
            Remove-Item -LiteralPath $checkedStage -Recurse -Force
        }
    }
}
Write-Output "Copied $copied save(s); skipped $skipped identical save(s)."
Write-Output "Load Game in Controller Lab now uses the copies in $targetSave"
Write-Output 'Original saves, existing target saves, settings and cloud files were not changed.'
