# Convenience wrapper around CMake for the native Windows build.
#
#   .\windows\build.ps1                 # Release build with the default toolchain
#   .\windows\build.ps1 -Test           # build and run the unit tests
#   .\windows\build.ps1 -Toolchain mingw
#
[CmdletBinding()]
param(
    [string]$BuildDir = (Join-Path $PSScriptRoot 'build'),
    [ValidateSet('auto', 'vs', 'mingw')]
    [string]$Toolchain = 'auto',
    [switch]$Test,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

$cmake = Get-Command cmake.exe -ErrorAction SilentlyContinue
if (-not $cmake) {
    throw 'CMake was not found in PATH. Install CMake 3.21+ or run pip install cmake.'
}

function Test-Command([string]$name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

if ($Toolchain -eq 'auto') {
    if (Test-Command 'cl.exe' -or (Test-Path 'C:\Program Files\Microsoft Visual Studio')) {
        $Toolchain = 'vs'
    } elseif (Test-Command 'g++.exe') {
        $Toolchain = 'mingw'
    } else {
        throw 'No C++ toolchain found. Install Visual Studio 2022 (Desktop C++) or put MinGW g++ in PATH.'
    }
}

if ($Clean -and (Test-Path $BuildDir)) {
    Write-Host "Removing $BuildDir"
    Remove-Item -Recurse -Force $BuildDir
}

if ($Toolchain -eq 'vs') {
    Write-Host 'Configuring with Visual Studio (x64)'
    & $cmake.Source -S $PSScriptRoot -B $BuildDir -A x64
    if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed' }
    & $cmake.Source --build $BuildDir --config Release --parallel
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    $exe = Join-Path $BuildDir 'Release\Lado.exe'
} else {
    Write-Host 'Configuring with MinGW Makefiles'
    & $cmake.Source -S $PSScriptRoot -B $BuildDir -G 'MinGW Makefiles' `
        -DCMAKE_BUILD_TYPE=Release
    if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed' }
    & $cmake.Source --build $BuildDir --parallel
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    $exe = Join-Path $BuildDir 'Lado.exe'
}

if ($Test) {
    $ctest = Get-Command ctest.exe -ErrorAction SilentlyContinue
    if (-not $ctest) { throw 'ctest was not found' }
    & $ctest.Source --test-dir $BuildDir -C Release --output-on-failure
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
}

Write-Host ''
Write-Host "Lado: $exe"
