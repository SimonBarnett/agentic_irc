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
    # Empty = auto: release third_party\nssm\win64\nssm.exe, then legacy C:\ai\ergo, then PATH (#266).
    [string]$Nssm = '',
    [string]$Launcher = '',
    [Alias('Home')]
    [string]$ConsoleHome = '',
    [string]$PasswordFile = '',
    [string[]]$Operators = @('Simon'),
    [string]$ServiceName = 'AircConsole'
)

$ErrorActionPreference = 'Stop'

# FR #259: $PSScriptRoot can be empty in param() defaults under [CmdletBinding()];
# resolve launcher dir in the body (also prefer local disk over mapped P:).
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    if ($PSCommandPath) { $scriptDir = Split-Path -Parent $PSCommandPath }
    elseif ($MyInvocation.MyCommand.Path) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
}
if (-not $Launcher) {
    if (-not $scriptDir) { throw 'cannot resolve Install-AircConsole.ps1 directory (FR #259)' }
    $Launcher = Join-Path $scriptDir 'Start-AircConsole.ps1'
}
$resolveHelper = Join-Path $scriptDir 'Resolve-AircConsoleNssm.ps1'
if (Test-Path -LiteralPath $resolveHelper) { . $resolveHelper }
elseif (Get-Command Resolve-AircConsoleNssmPath -ErrorAction SilentlyContinue) { }
else {
    function Resolve-AircConsoleNssmPath {
        param([string]$Preferred = '', [string]$ScriptDir = '')
        if ($Preferred -and (Test-Path -LiteralPath $Preferred)) { return (Resolve-Path -LiteralPath $Preferred).Path }
        return $null
    }
}
$resolvedNssm = Resolve-AircConsoleNssmPath -Preferred $Nssm -ScriptDir $scriptDir
if (-not $resolvedNssm) {
    throw 'nssm missing: unpack third_party\nssm\win64\nssm.exe from the release zip (issue #266), or pass -Nssm, or install to C:\ai\ergo\nssm.exe'
}
$Nssm = $resolvedNssm
Write-Host "INFO using nssm: $Nssm"
if (-not (Test-Path -LiteralPath $Launcher)) { throw "launcher missing: $Launcher" }
$Launcher = (Resolve-Path -LiteralPath $Launcher).Path
if ($Launcher -match '^[A-Za-z]:\\' ) {
    # Warn when launcher is on a mapped network drive (issue #259 repro on P:).
    $root = ($Launcher.Substring(0, 2))
    $drive = Get-PSDrive -Name $root.TrimEnd(':') -ErrorAction SilentlyContinue
    if ($drive -and $drive.DisplayRoot) {
        Write-Host ("WARN launcher on mapped drive {0} -> {1}; prefer a local copy under C:\\ai\\airc-console (FR #259)" -f $root, $drive.DisplayRoot)
    }
}

if (-not $ConsoleHome) {
    $ConsoleHome = Join-Path $env:USERPROFILE '.airc-console'
}
New-Item -ItemType Directory -Force -Path $ConsoleHome | Out-Null
$opsFile = Join-Path $ConsoleHome 'operators.txt'
if (-not (Test-Path -LiteralPath $opsFile) -and $Operators.Count -gt 0) {
    Set-Content -LiteralPath $opsFile -Value ($Operators -join "`n") -Encoding utf8
}

function Invoke-AircNssm {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][string[]]$NssmArgs
    )
    # nssm writes status to stderr even on success ("STOP: The service has not been
    # started"). Under $ErrorActionPreference=Stop that becomes NativeCommandError (#273).
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @NssmArgs 2>&1
        $code = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEa
    }
    return [pscustomobject]@{
        ExitCode = $code
        Output   = @($out | ForEach-Object { "$_" })
    }
}

function Remove-AircConsoleService {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][string]$Name
    )
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "INFO no existing $Name service"
        return
    }
    Write-Host "INFO removing existing $Name (status=$($svc.Status))"
    $null = Invoke-AircNssm -Exe $Exe -NssmArgs @('stop', $Name)
    Start-Sleep -Seconds 2
    # confirm = non-interactive remove
    $rm = Invoke-AircNssm -Exe $Exe -NssmArgs @('remove', $Name, 'confirm')
    Start-Sleep -Seconds 1
    $left = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($left) {
        # Fallback when nssm remove is sticky
        sc.exe delete $Name 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        $left = Get-Service -Name $Name -ErrorAction SilentlyContinue
    }
    if ($left) {
        throw ("failed to remove existing service {0}; nssm exit={1} out={2}" -f $Name, $rm.ExitCode, ($rm.Output -join ' '))
    }
    Write-Host "INFO removed $Name"
}

# Issue #273: always tear down any prior install, then register from this tree.
Remove-AircConsoleService -Exe $Nssm -Name $ServiceName
Write-Host "INFO Installing $ServiceName"
$inst = Invoke-AircNssm -Exe $Nssm -NssmArgs @('install', $ServiceName, 'powershell.exe')
if ($inst.ExitCode -ne 0) {
    throw ("nssm install failed: {0} ({1})" -f $inst.ExitCode, ($inst.Output -join ' '))
}

# #271: always wire console.password path (Python mints GUID if missing).
if (-not $PasswordFile) {
    $PasswordFile = Join-Path $ConsoleHome 'console.password'
}

# Application MUST be powershell.exe (never the .ps1 Path — see NSSM GUI / issue #259).
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`" -ServiceMode -ConsoleHome `"$ConsoleHome`""
$appParams += " -PasswordFile `"$PasswordFile`""
if (Test-Path -LiteralPath $opsFile) { $appParams += " -OperatorsFile `"$opsFile`"" }

$setPairs = @(
    @('Application', 'powershell.exe'),
    @('AppDirectory', (Split-Path $Launcher -Parent)),
    @('AppParameters', $appParams),
    @('DisplayName', 'airc console (#{machine} IRC shell)'),
    @('Description', 'FR #253: nick console on #{machinename}; auth PRIVMSG -> shell; silent in channel.'),
    @('Start', 'SERVICE_AUTO_START'),
    @('AppExit', 'Default', 'Restart'),
    @('AppRestartDelay', '5000'),
    @('AppThrottle', '1500'),
    @('ObjectName', 'LocalSystem')
)
$logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'airc-console-service.log'
$setPairs += @(
    @('AppStdout', $log),
    @('AppStderr', $log),
    @('AppStdoutCreationDisposition', '4'),
    @('AppStderrCreationDisposition', '4'),
    @('AppRotateFiles', '1'),
    @('AppRotateBytes', '1048576')
)
foreach ($pair in $setPairs) {
    $argsN = @('set', $ServiceName) + $pair
    $r = Invoke-AircNssm -Exe $Nssm -NssmArgs $argsN
    if ($r.ExitCode -ne 0) {
        throw ("nssm set failed ({0}): {1}" -f ($pair -join ' '), ($r.Output -join ' '))
    }
}

icacls $ConsoleHome /grant 'SYSTEM:(OI)(CI)(M)' /T 2>$null | Out-Null
if ($PasswordFile -and (Test-Path -LiteralPath $PasswordFile)) {
    icacls $PasswordFile /grant 'SYSTEM:(R)' 2>$null | Out-Null
}

$appGet = Invoke-AircNssm -Exe $Nssm -NssmArgs @('get', $ServiceName, 'Application')
$parGet = Invoke-AircNssm -Exe $Nssm -NssmArgs @('get', $ServiceName, 'AppParameters')
Write-Host ("Application=" + ($appGet.Output -join ' ').Trim())
Write-Host ("AppParameters=" + ($parGet.Output -join ' ').Trim())
Get-Service $ServiceName | Format-Table Name, Status, StartType -AutoSize
Write-Host 'INFO Install done (prior service removed if present; #273).'
Write-Host 'INFO Operators: ~\.airc-console\operators.txt (seeded if missing).'
Write-Host 'INFO NickServ password: auto GUID in ~\.airc-console\console.password on first start (#271).'
Write-Host 'INFO Ergo server PASS: AGENTIC_IRC_PASSWORD or ~\.airc-console\ergo.password / ~\.grok\ergo\connect.password.'
Write-Host 'INFO Then: Start-Service AircConsole'
