#Requires -Version 5.1
<#
.SYNOPSIS
  Launch airc console service host (FR #253). Use -ServiceMode under NSSM.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Python = '',
    [string]$HostName = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Nick = 'console',
    [string]$Home = '',
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
if (-not $RepoRoot -or -not (Test-Path -LiteralPath $RepoRoot)) {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}
$script = Join-Path $PSScriptRoot 'airc_console_service.py'
if (-not (Test-Path -LiteralPath $script)) { throw "missing $script" }

if (-not $Python) {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $py) { throw 'python.exe not on PATH' }
    $Python = $py.Source
}

if (-not $Home) {
    $Home = Join-Path $env:USERPROFILE '.airc-console'
}
New-Item -ItemType Directory -Force -Path $Home | Out-Null

$argsList = @(
    $script,
    '--host', $HostName,
    '--port', "$Port",
    '--nick', $Nick,
    '--home', $Home
)
if ($PasswordFile) { $argsList += @('--password-file', $PasswordFile) }
if ($OperatorsFile) { $argsList += @('--operators-file', $OperatorsFile) }
elseif (Test-Path -LiteralPath (Join-Path $Home 'operators.txt')) {
    $argsList += @('--operators-file', (Join-Path $Home 'operators.txt'))
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

Write-Host ("INFO Start-AircConsole ServiceMode={0} home={1}" -f [bool]$ServiceMode, $Home)
& $Python @argsList
exit $LASTEXITCODE
