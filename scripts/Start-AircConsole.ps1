#Requires -Version 5.1
<#
.SYNOPSIS
  Launch airc console service host (FR #253). Use -ServiceMode under NSSM.
.NOTES
  FR #259: never use $PSScriptRoot inside param() defaults — it can be empty
  when invoked via .cmd / -File on some hosts (Split-Path empty Path error).
  Do not name a parameter $Home — that automatic variable is read-only.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$Python = '',
    [string]$HostName = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Nick = 'console',
    [string]$ConsoleHome = '',
    [string]$PasswordFile = '',
    [string[]]$Operators = @(),
    [string]$OperatorsFile = '',
    [string[]]$Accounts = @(),
    [switch]$RequireAccount,
    [switch]$TlsInsecure,
    [switch]$ServiceMode,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'

function Get-AircScriptDir {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($PSCommandPath) { return Split-Path -Parent $PSCommandPath }
    if ($MyInvocation.MyCommand.Path) { return Split-Path -Parent $MyInvocation.MyCommand.Path }
    throw 'cannot resolve airc scripts directory (PSScriptRoot empty)'
}

$scriptDir = Get-AircScriptDir
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $scriptDir
}
$script = Join-Path $scriptDir 'airc_console_service.py'
if (-not (Test-Path -LiteralPath $script)) { throw "missing $script" }

if (-not $Python) {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $py) { throw 'python.exe not on PATH' }
    $Python = $py.Source
}

if (-not $ConsoleHome) {
    $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
}
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null

$argsList = @(
    $script,
    '--host', $HostName,
    '--port', "$Port",
    '--nick', $Nick,
    '--home', $ConsoleHome
)
if ($PasswordFile) { $argsList += @('--password-file', $PasswordFile) }
if ($OperatorsFile) { $argsList += @('--operators-file', $OperatorsFile) }
elseif (Test-Path -LiteralPath (Join-Path $ConsoleHome 'operators.txt')) {
    $argsList += @('--operators-file', (Join-Path $ConsoleHome 'operators.txt'))
}
if ($Operators.Count -gt 0) {
    $argsList += '--operators'
    $argsList += $Operators
}
if ($Accounts.Count -gt 0) {
    $argsList += '--accounts'
    $argsList += $Accounts
}
if ($RequireAccount) { $argsList += '--require-account' }
if ($TlsInsecure) { $argsList += '--tls-insecure' }
if ($SelfTest) { $argsList += '--selftest' }

Write-Host ("INFO Start-AircConsole ServiceMode={0} home={1} scriptDir={2}" -f [bool]$ServiceMode, $ConsoleHome, $scriptDir)
& $Python @argsList
exit $LASTEXITCODE
