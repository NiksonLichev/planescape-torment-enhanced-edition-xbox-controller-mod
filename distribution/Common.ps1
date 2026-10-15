Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$script:ModFiles = @('engine.lua','ControllerLab.exe','override/M_PSTPAD.lua','override/pstcontroller.dll','override/UI.menu','Play-Controller-Mod.cmd','override/PSTPRAD.bam','override/PSTPSEL.bam')

function Resolve-GameFolder([string]$GamePath) {
    if (-not $GamePath) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Select your Planescape Torment Enhanced Edition working copy (contains Torment.exe)'
        if ($picker.ShowDialog() -ne 'OK') { throw 'Cancelled. No game files changed.' }
        $GamePath = $picker.SelectedPath
        $picker.Dispose()
    }
    $folder = Get-Item -LiteralPath $GamePath
    if (-not $folder.PSIsContainer) { throw 'Select a game folder, not a file.' }
    if ($folder.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Choose a regular folder, not a directory link.' }
    return $folder.FullName.TrimEnd('\','/')
}

function Get-SafePath([string]$Root,[string]$Relative) {
    $path = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    $prefix = $Root.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $path.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes the selected folder.' }
    $probe = $path
    while ($probe.Length -ge $Root.Length) {
        if (Test-Path -LiteralPath $probe) {
            if ((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked path is not supported: $probe" }
        }
        if ($probe -eq $Root) { break }
        $probe = [IO.Path]::GetDirectoryName($probe)
    }
    return $path
}

function Get-ByteHash([byte[]]$Bytes) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
    finally { $hash.Dispose() }
}
function Get-PathHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}
function Write-Utf8([string]$Path,[string]$Text) { [IO.File]::WriteAllText($Path,$Text,$script:Utf8) }

function Assert-GameClosed([string]$Root) {
    foreach ($process in @(Get-Process -Name Torment -ErrorAction SilentlyContinue)) {
        try { $path = $process.Path } catch { throw 'Cannot inspect Torment. Close it before installing.' }
        if (-not $path -or $path -eq (Join-Path $Root 'Torment.exe')) { throw 'Close the selected game before installing or uninstalling.' }
    }
    # Process enumeration can be restricted. A non-sharing write handle also
    # catches mapped executable/DLL images. No bytes are written by this probe.
    foreach ($relative in @('Torment.exe','override/pstcontroller.dll')) {
        $path = Get-SafePath $Root $relative
        if (Test-Path -LiteralPath $path) {
            try { $stream = [IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None); $stream.Dispose() }
            catch { throw "Game file is in use or not writable. Close the game and use a writable copy: $relative" }
        }
    }
}

function Read-UInt32([byte[]]$Bytes,[long]$Offset) {
    if ($Offset -lt 0 -or $Offset+4 -gt $Bytes.Length) { throw 'Truncated game resource index.' }
    return [BitConverter]::ToUInt32($Bytes,[int]$Offset)
}
function Read-UInt16([byte[]]$Bytes,[long]$Offset) {
    if ($Offset -lt 0 -or $Offset+2 -gt $Bytes.Length) { throw 'Truncated game resource index.' }
    return [BitConverter]::ToUInt16($Bytes,[int]$Offset)
}
function Read-GameUI([string]$Root) {
    $key = [IO.File]::ReadAllBytes((Get-SafePath $Root 'chitin.key'))
    if ($key.Length -lt 24 -or [Text.Encoding]::ASCII.GetString($key,0,8) -ne 'KEY V1  ') { throw 'Unsupported chitin.key format.' }
    $bifCount = Read-UInt32 $key 8; $count = Read-UInt32 $key 12
    $bifTable = Read-UInt32 $key 16; $table = Read-UInt32 $key 20
    if ([long]$table+[long]$count*14 -gt $key.Length -or [long]$bifTable+[long]$bifCount*12 -gt $key.Length) { throw 'Invalid KEY table bounds.' }
    $locator = $null
    for ($index=0; $index -lt $count; $index++) {
        $offset = [long]$table+$index*14
        $name = [Text.Encoding]::ASCII.GetString($key,[int]$offset,8).TrimEnd([char]0)
        if ($name -eq 'UI' -and (Read-UInt16 $key ($offset+8)) -eq 0x408) {
            if ($null -ne $locator) { throw 'Duplicate UI resource.' }
            $locator = Read-UInt32 $key ($offset+10)
        }
    }
    if ($null -eq $locator) { throw 'UI.menu was not found in game resources.' }
    $bifIndex = $locator -shr 20
    if ($bifIndex -ge $bifCount) { throw 'Invalid BIFF index.' }
    $entry = [long]$bifTable+$bifIndex*12
    $nameOffset = Read-UInt32 $key ($entry+4); $nameLength = Read-UInt16 $key ($entry+8)
    if ([long]$nameOffset+$nameLength -gt $key.Length) { throw 'Invalid BIFF filename.' }
    $bifName = [Text.Encoding]::ASCII.GetString($key,[int]$nameOffset,$nameLength).TrimEnd([char]0)
    $stream = [IO.File]::OpenRead((Get-SafePath $Root $bifName))
    $reader = New-Object IO.BinaryReader($stream)
    try {
        $header = $reader.ReadBytes(20)
        if ($header.Length -ne 20 -or [Text.Encoding]::ASCII.GetString($header,0,8) -ne 'BIFFV1  ') { throw 'Unsupported BIFF format.' }
        $fileCount = Read-UInt32 $header 8; $fileTable = Read-UInt32 $header 16
        if ([long]$fileTable+[long]$fileCount*16 -gt $stream.Length) { throw 'Invalid BIFF table bounds.' }
        $stream.Position = $fileTable; $matches = @()
        for ($index=0; $index -lt $fileCount; $index++) {
            $id = $reader.ReadUInt32(); $offset = $reader.ReadUInt32(); $length = $reader.ReadUInt32()
            $kind = $reader.ReadUInt16(); $null = $reader.ReadUInt16()
            if (($id -band 0x3fff) -eq ($locator -band 0x3fff)) { $matches += @{offset=$offset; length=$length; kind=$kind} }
        }
        if ($matches.Count -ne 1 -or $matches[0].kind -ne 0x408) { throw 'Invalid BIFF UI locator.' }
        $resource = $matches[0]
        if ([long]$resource.offset+[long]$resource.length -gt $stream.Length -or $resource.length -gt [int]::MaxValue) { throw 'Truncated UI resource.' }
        $stream.Position = $resource.offset; $bytes = $reader.ReadBytes([int]$resource.length)
        $text = $script:Utf8.GetString($bytes).TrimStart([char]0xfeff)
        return $text.Replace("`r`n","`n").Replace("`r","`n")
    } finally { $reader.Dispose(); $stream.Dispose() }
}

function Apply-UiPatch([string]$Text,$Patch) {
    $bytes = $script:Utf8.GetBytes($Text)
    if ((Get-ByteHash $bytes) -ne $Patch.sourceSha256) { throw 'The stock UI differs from the supported build. No files changed.' }
    $output = New-Object IO.MemoryStream
    try {
        [long]$cursor = 0
        foreach ($hunk in $Patch.hunks) {
            [long]$start = $hunk.start; [long]$delete = $hunk.delete
            if ($start -lt $cursor -or $delete -lt 0 -or $start+$delete -gt $bytes.Length) { throw 'Invalid UI patch bounds.' }
            $output.Write($bytes,[int]$cursor,[int]($start-$cursor))
            $insert = [Convert]::FromBase64String($hunk.insert)
            $output.Write($insert,0,$insert.Length); $cursor = $start+$delete
        }
        $output.Write($bytes,[int]$cursor,[int]($bytes.Length-$cursor))
        $result = $output.ToArray()
        if ((Get-ByteHash $result) -ne $Patch.targetSha256) { throw 'UI patch output checksum failed.' }
        return ,$result
    } finally { $output.Dispose() }
}

function Restore-ModFiles([string]$Root,$State,[bool]$CheckInstalled) {
    if ($State.backupSet -notmatch '^[a-f0-9]{32}$') { throw 'Invalid backup set.' }
    foreach ($entry in $State.files) {
        if ($script:ModFiles -notcontains $entry.path -or $entry.backup -notmatch '^\d{2}\.bin$') { throw 'Invalid backup manifest.' }
        $target = Get-SafePath $Root $entry.path
        if ($CheckInstalled) {
            if (-not (Test-Path -LiteralPath $target) -or (Get-PathHash $target) -ne $entry.installedHash) {
                throw "File changed after installation; keep your edits and backups. Restore manually: $($entry.path)"
            }
        }
        if ($entry.existed) {
            $backup = Get-SafePath $Root ('.pstcontroller/backups/'+$State.backupSet+'/'+$entry.backup)
            if (-not (Test-Path -LiteralPath $backup) -or (Get-PathHash $backup) -ne $entry.originalHash) { throw 'Backup checksum failed.' }
        }
    }
    foreach ($entry in $State.files) {
        $target = Get-SafePath $Root $entry.path
        if ($entry.existed) { [IO.File]::Copy((Get-SafePath $Root ('.pstcontroller/backups/'+$State.backupSet+'/'+$entry.backup)),$target,$true) }
        elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
    }
}
