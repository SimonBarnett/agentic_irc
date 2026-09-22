$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Agentic Build IRC"
Set-Location -LiteralPath "C:\ai"
$env:Path = "C:\Python312;C:\Python312\Scripts;C:\Users\medatech.si\AppData\Local\Programs\Python\Python312;" + $env:Path
$ircHome = Join-Path $env:USERPROFILE ".agentic-irc-cursor-2"
& (Join-Path $PSScriptRoot "Start-TalkSeat.ps1") -MachineId ce-priority-dev1 -IrcHome $ircHome -Scripts $PSScriptRoot
Write-Host ("INFO seat={0} home={1} starting cursor-agent" -f $PID, $ircHome)
$promptFile = Join-Path $PSScriptRoot "bootstrap-second-seat-dev1.txt"
$prompt = Get-Content -LiteralPath $promptFile -Raw
$agent = Join-Path $env:LOCALAPPDATA "cursor-agent\cursor-agent.ps1"
& $agent --trust --force --workspace C:\ai --model grok-4.6 -- $prompt
