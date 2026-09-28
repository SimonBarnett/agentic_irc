#Requires -Version 5.1
<#
.SYNOPSIS
  Launch airc console service host (FR #253). Use -ServiceMode under NSSM.

.NOTES
  FR #259: do not use $PSScriptRoot in param() defaults. With [CmdletBinding()],
  Windows PowerShell 5.1 leaves $PSScriptRoot empty while evaluating defaults
  (mapped drives / download zips included). Resolve the script dir in the body.

  Never name a parameter $Home — PowerShell's automatic $Home is read-only and
  binding -Home fails with VariableNotWritable (same class of seat bugs).
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$Python = '',
    [string]$HostName = 'irc.ntsa.uk',
    [int]$Port = 6697,
    # Empty/auto -> Python console-<machine> (issue #286; bare console hits 433).
    [string]$Nick = 'auto',
    [Alias('Home')]
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

function Get-AircConsoleScriptDir {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($PSCommandPath) { return (Split-Path -Parent $PSCommandPath) }
    if ($MyInvocation.MyCommand.Path) {
        return (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
    throw 'cannot resolve Start-AircConsole.ps1 directory (FR #259)'
}

$scriptDir = Get-AircConsoleScriptDir
if (-not $RepoRoot -or -not (Test-Path -LiteralPath $RepoRoot)) {
    $RepoRoot = Split-Path -Parent $scriptDir
}
$script = Join-Path $scriptDir 'airc_console_service.py'
if (-not (Test-Path -LiteralPath $script)) { throw "missing $script" }

if (-not $ConsoleHome) {
    $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
}
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null

# Issue #282: LocalSystem service has no user PATH — resolve absolute python.exe.
$resolvePy = Join-Path $scriptDir 'Resolve-AircConsolePython.ps1'
if (Test-Path -LiteralPath $resolvePy) { . $resolvePy }
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    $hint = ''
    if ($ConsoleHome -match '^(.*)\\\.airc-console\\?$') {
        $hint = $Matches[1]
    } elseif ($env:USERPROFILE) {
        $hint = $env:USERPROFILE
    }
    if (Get-Command Resolve-AircConsolePythonPath -ErrorAction SilentlyContinue) {
        $Python = Resolve-AircConsolePythonPath -Preferred $Python -HintUserProfile $hint
    }
}
if (-not $Python) {
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($py) { $Python = $py.Source }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'python.exe not found (LocalSystem has no PATH; pass -Python or install Python for all users). Issue #282.'
}
$Python = (Resolve-Path -LiteralPath $Python).Path
Write-Host "INFO python=$Python"

$argsList = @(
    $script,
    '--host', $HostName,
    '--port', "$Port",
    '--nick', $Nick,
    '--home', $ConsoleHome
)
# #271: always point at console.password — Python mints a GUID if missing.
if (-not $PasswordFile) {
    $PasswordFile = Join-Path $ConsoleHome 'console.password'
}
$argsList += @('--password-file', $PasswordFile)
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
