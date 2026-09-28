#Requires -Version 5.1
<#
.SYNOPSIS
  Build installable release zip for airc console (FR #253).
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$OutDir = '',
    [string]$Version = ''
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
    if ($PSScriptRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    } else {
        $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
}
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $Version) {
    $verFile = Join-Path $RepoRoot 'src\airc_console\VERSION'
    if (Test-Path -LiteralPath $verFile) {
        $Version = (Get-Content $verFile -Raw).Trim()
    } else {
        $Version = '0.1.0'
    }
}

$stage = Join-Path $OutDir ("airc-console-$Version")
if (Test-Path -LiteralPath $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$files = @(
    'scripts\airc_console.py',
    'scripts\airc_console_service.py',
    'scripts\account_map.py',
    'scripts\Start-AircConsole.ps1',
    'scripts\Start-AircConsole.cmd',
    'scripts\Install-AircConsole.ps1',
    'scripts\Install-AircConsole.cmd',
    'docs\airc-console-fr253.md',
    'src\airc_console\VERSION',
    'src\airc_console\README.md'
)
foreach ($rel in $files) {
    $src = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $src)) { throw "missing $rel" }
    $dest = Join-Path $stage $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dest -Force
}

# Selftest before zip
$py = (Get-Command python.exe).Source
& $py (Join-Path $stage 'scripts\airc_console_service.py') --selftest
if ($LASTEXITCODE -ne 0) { throw "selftest failed: $LASTEXITCODE" }

$zip = Join-Path $OutDir ("airc-console-$Version.zip")
if (Test-Path -LiteralPath $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
Set-Content -LiteralPath ($zip + '.sha256') -Value ("$hash  airc-console-$Version.zip") -Encoding ascii
Write-Host "INFO packed $zip"
Write-Host "INFO sha256 $hash"
Get-Item $zip, ($zip + '.sha256') | Format-Table Name, Length -AutoSize
