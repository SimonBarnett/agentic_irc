param(
    [int]$WaitForPid = 0,
    [int]$WaitSec = 300,
    [string]$IrcHome = '',
    [string]$Title = 'Agentic Build IRC'
)
$ErrorActionPreference = 'Stop'
if (-not $IrcHome) { $IrcHome = Join-Path $env:USERPROFILE '.agentic-irc-cursor-2' }
$here = $PSScriptRoot
$child = Join-Path $here '_Run-SecondSeatTui.ps1'
if ($WaitForPid -gt 0) {
    $deadline = (Get-Date).AddSeconds($WaitSec)
    Write-Output ('INFO waiting for pid {0} to exit' -f $WaitForPid)
    while ((Get-Process -Id $WaitForPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    if (Get-Process -Id $WaitForPid -ErrorAction SilentlyContinue) { Write-Error ('timeout waiting for pid {0}' -f $WaitForPid) }
    Write-Output ('INFO pid {0} gone' -f $WaitForPid)
}
$stop = 'C:\ai\agentic_build\tools\Stop-HungAgent.ps1'
if (Test-Path -LiteralPath $stop) { & $stop -IrcHome $IrcHome }
$ps = (Get-Command powershell.exe).Source
$proc = Start-Process -FilePath $ps -ArgumentList @('-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File',$child) -WorkingDirectory 'C:\ai' -PassThru
Write-Output ('INFO started second-seat powershell pid={0}' -f $proc.Id)
