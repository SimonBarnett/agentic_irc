# Start or reuse irc_listen TSR for a talk-seat home. Writes coordinator.pid.
# Seat id: nick suffix and digest pid = agent= (irc_agent.py), never listen=.
# Prefer scripts/Start-TalkSeat.ps1 to start agent + listener with correct nick.
# Do not use $Home (read-only). Does not start a second listener or irc_agent.
param(
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = 'C:\ai\agentic_irc\scripts'
)
$ErrorActionPreference = 'Stop'
$resolved = [Environment]::ExpandEnvironmentVariables($IrcHome)
if (-not (Test-Path -LiteralPath $resolved)) {
    New-Item -ItemType Directory -Force -Path $resolved | Out-Null
}
$listen = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'irc_listen.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
    Select-Object -First 1
if (-not $listen) {
    $py = (Get-Command python -ErrorAction Stop).Source
    $listenPath = Join-Path $Scripts 'irc_listen.py'
    $proc = Start-Process -FilePath $py -ArgumentList @('-u', $listenPath, '--home', $resolved) -WindowStyle Hidden -PassThru
    $listenPid = $proc.Id
} else {
    $listenPid = $listen.ProcessId
}
$agent = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'irc_agent.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
    Select-Object -First 1
$agentPid = if ($agent) { $agent.ProcessId } else { '' }
$nick = ''
if ($agent -and $agent.CommandLine -match '--nick\s+(\S+)') { $nick = $Matches[1] }
@(
    "nick=$nick"
    "listen=$listenPid"
    "agent=$agentPid"
    "home=$resolved"
) | Set-Content -LiteralPath (Join-Path $resolved 'coordinator.pid') -Encoding utf8
Write-Output "INFO TSR listen=$listenPid agent=$agentPid nick=$nick"