param([switch]$Check,[string]$CompilerPath)
$ErrorActionPreference = 'Stop'
$taskCompiler = $CompilerPath
if (-not $taskCompiler) { $taskCompiler = Join-Path $PSScriptRoot 'tools\zig-x86_64-windows-0.15.2\zig.exe' }
if (-not (Test-Path -LiteralPath $taskCompiler)) {
    $taskCompilerCommand = Get-Command zig -ErrorAction SilentlyContinue
    if (-not $taskCompilerCommand) { throw 'Provide Zig 0.15.2 with -CompilerPath or install it on PATH.' }
    $taskCompiler = $taskCompilerCommand.Source
}
$taskNativeSource = Join-Path $PSScriptRoot 'native\pstcontroller.c'
$taskOutput = Join-Path $PSScriptRoot 'native\pstcontroller.dll'
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $PSScriptRoot 'tools\zig-cache'
$env:ZIG_LOCAL_CACHE_DIR = Join-Path $PSScriptRoot 'tools\zig-local-cache'
& $taskCompiler cc -target x86_64-windows-gnu -shared -O2 -Wall -Wextra -Werror $taskNativeSource -o $taskOutput -lbcrypt -luser32 -lkernel32
if ($LASTEXITCODE -ne 0) { throw "Native build failed: $LASTEXITCODE" }
Write-Output "Built $taskOutput"
$taskLoaderSource = Join-Path $PSScriptRoot 'native\controller_loader.c'
$taskLoaderOutput = Join-Path $PSScriptRoot 'native\ControllerLab.exe'
& $taskCompiler cc -target x86_64-windows-gnu -municode '-Wl,--subsystem,windows' -O2 -Wall -Wextra -Werror $taskLoaderSource -o $taskLoaderOutput -luser32 -lkernel32
if ($LASTEXITCODE -ne 0) { throw "Loader build failed: $LASTEXITCODE" }
Write-Output "Built $taskLoaderOutput"
if ($Check) {
    $taskTestSource = Join-Path $PSScriptRoot 'native\test_native.c'
    $taskTestOutput = Join-Path $PSScriptRoot 'native\test_native.exe'
    & $taskCompiler cc -target x86_64-windows-gnu -O2 -Wall -Wextra -Werror $taskTestSource -o $taskTestOutput -lbcrypt -luser32 -lkernel32
    if ($LASTEXITCODE -ne 0) { throw "Native test build failed: $LASTEXITCODE" }
    & $taskTestOutput
    if ($LASTEXITCODE -ne 0) { throw "Native test failed: $LASTEXITCODE" }
}
