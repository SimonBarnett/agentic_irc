$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Agentic Build IRC'
Set-Location -LiteralPath 'C:\ai'
$ircHome = Join-Path $env:USERPROFILE '.agentic-irc-cursor-2'
& (Join-Path $PSScriptRoot 'Start-TalkSeat.ps1') -MachineId flamingo -IrcHome $ircHome -Scripts $PSScriptRoot
Write-Host ('INFO seat={0} home={1} starting cursor-agent' -f $PID, $ircHome)
$promptFile = Join-Path $PSScriptRoot 'bootstrap-second-seat.txt'
$prompt = Get-Content -LiteralPath $promptFile -Raw
$agent = Join-Path $env:LOCALAPPDATA 'cursor-agent\cursor-agent.ps1'
& $agent --trust --force --workspace C:\ai --model grok-4.6 -- $prompt
