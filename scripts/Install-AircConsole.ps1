#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Register NSSM service AircConsole (Automatic). FR #253 / #256.
.NOTES
  Downloaded zips are unsigned. Prefer Install-AircConsole.cmd (Unblock-File +
  -ExecutionPolicy Bypass). Direct .ps1 invoke fails under AllSigned/Restricted.
#>
[CmdletBinding()]
param(
    [string]$Nssm = 'C:\ai\ergo\nssm.exe',
    [string]$Launcher = '',
    [string]$ConsoleHome = '',
    [string]$PasswordFile = '',
    [string[]]$Operators = @('Simon'),
    [string]$ServiceName = 'AircConsole'
)

$ErrorActionPreference = 'Stop'
# FR #259: resolve script dir in body — $PSScriptRoot may be empty in param defaults.
# Do not name a parameter $Home (automatic variable is read-only).
$scriptDir = $PSScriptRoot
if (-not $scriptDir -and $PSCommandPath) { $scriptDir = Split-Path -Parent $PSCommandPath }
if (-not $scriptDir -and $MyInvocation.MyCommand.Path) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { throw 'cannot resolve Install-AircConsole script directory' }
if (-not $Launcher) {
    $Launcher = Join-Path $scriptDir 'Start-AircConsole.ps1'
}
if (-not $ConsoleHome) {
    $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
}
if (-not (Test-Path -LiteralPath $Nssm)) { throw "nssm missing: $Nssm" }
if (-not (Test-Path -LiteralPath $Launcher)) { throw "launcher missing: $Launcher" }

New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null
$opsFile = Join-Path $ConsoleHome 'operators.txt'
if (-not (Test-Path -LiteralPath $opsFile) -and $Operators.Count -gt 0) {
    Set-Content -LiteralPath $opsFile -Value ($Operators -join "`n") -Encoding utf8
}

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "INFO $ServiceName exists; reconfiguring"
    & $Nssm stop $ServiceName 2>$null | Out-Null
    Start-Sleep -Seconds 2
} else {
    Write-Host "INFO Installing $ServiceName"
    & $Nssm install $ServiceName powershell.exe
    if ($LASTEXITCODE -ne 0) { throw "nssm install failed: $LASTEXITCODE" }
}

$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`" -ServiceMode -ConsoleHome `"$ConsoleHome`""
if ($PasswordFile) { $appParams += " -PasswordFile `"$PasswordFile`"" }
if (Test-Path -LiteralPath $opsFile) { $appParams += " -OperatorsFile `"$opsFile`"" }

& $Nssm set $ServiceName Application powershell.exe
& $Nssm set $ServiceName AppDirectory (Split-Path $Launcher -Parent)
& $Nssm set $ServiceName AppParameters $appParams
& $Nssm set $ServiceName DisplayName 'airc console (#{machine} IRC shell)'
& $Nssm set $ServiceName Description 'FR #253: nick console on #{machinename}; auth PRIVMSG -> shell; silent in channel.'
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppExit Default Restart
& $Nssm set $ServiceName AppRestartDelay 5000
& $Nssm set $ServiceName AppThrottle 1500
& $Nssm set $ServiceName ObjectName LocalSystem

$logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'airc-console-service.log'
& $Nssm set $ServiceName AppStdout $log
& $Nssm set $ServiceName AppStderr $log
& $Nssm set $ServiceName AppStdoutCreationDisposition 4
& $Nssm set $ServiceName AppStderrCreationDisposition 4
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 1048576

icacls $ConsoleHome /grant 'SYSTEM:(OI)(CI)(M)' /T 2>$null | Out-Null
if ($PasswordFile -and (Test-Path -LiteralPath $PasswordFile)) {
    icacls $PasswordFile /grant 'SYSTEM:(R)' 2>$null | Out-Null
}

Write-Host ("Application=" + (& $Nssm get $ServiceName Application))
Write-Host ("AppParameters=" + (& $Nssm get $ServiceName AppParameters))
Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install done. Configure password file + operators before Start-Service.'
