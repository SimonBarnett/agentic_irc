# Start or reuse irc_agent + irc_listen for a talk seat.
# Nick = {machine-id}-{SeatPid} where SeatPid is this PowerShell session $PID (not python children).
# Keep this PowerShell session alive while the talk seat is in use (seat= in coordinator.pid).
# Detached irc_listen is started via Start-IrcTsr.ps1; tail $IrcHome/listen.stdout.log for wakes.
param(
    [Parameter(Mandatory = $true)]
    [string]$MachineId,
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = 'C:\ai\agentic_irc\scripts',
    [string]$IrcHost = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Channel = ''
)
$ErrorActionPreference = 'Stop'
$SeatPid = $PID
$mid = $MachineId.Trim().ToLower()
if (-not $Channel) {
    # Fleet + shop + FR talk room (issue #108).
    $Channel = "#bobiverse,#$mid,#agentic_irc"
}
$resolved = [Environment]::ExpandEnvironmentVariables($IrcHome)
if (-not (Test-Path -LiteralPath $resolved)) {
    New-Item -ItemType Directory -Force -Path $resolved | Out-Null
}
$expectedNick = "$mid-$SeatPid"
$env:AGENTIC_IRC_SEAT_PID = "$SeatPid"
$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (-not (Test-Path -LiteralPath $pwFile)) {
    Write-Error "missing connect.password at $pwFile"
}
$env:AGENTIC_IRC_PASSWORD = (Get-Content -LiteralPath $pwFile -Raw).Trim()
$env:AGENTIC_IRC_DEBUG = '1'
$py = (Get-Command python -ErrorAction Stop).Source
$agentPath = Join-Path $Scripts 'irc_agent.py'
$guardPath = Join-Path $Scripts 'talk_seat_pid.py'
function Get-HomePythonProcs {
    param([string]$HomePath)
    $agentProc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'irc_agent.py' -and $_.CommandLine -match [regex]::Escape($HomePath) } |
        Select-Object -First 1
    $listenProc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'irc_listen.py' -and $_.CommandLine -match [regex]::Escape($HomePath) } |
        Select-Object -First 1
    return $agentProc, $listenProc
}
function Stop-CursorHomeAgents {
    param([string]$HomePath)
    $gracePath = Join-Path $Scripts 'agent_control.py'
    if (Test-Path -LiteralPath $gracePath) {
        & $py $gracePath --home $HomePath --reason 'talk-seat recycle' --wait-s 12 2>&1 | Out-Null
    }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -match 'irc_(agent|listen)\.py' -and
            $_.CommandLine -match [regex]::Escape($HomePath)
        } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 400
}
function Assert-HomeBind {
    param(
        [string]$HomePath,
        [string]$ExpectedNick,
        [string]$LiveAgentNick,
        [bool]$LiveListen
    )
    $bindArgs = @(
        $guardPath,
        '--bind-home',
        '--home', $HomePath,
        '--expected-nick', $ExpectedNick
    )
    if ($LiveAgentNick) { $bindArgs += @('--live-agent-nick', $LiveAgentNick) }
    if ($LiveListen) { $bindArgs += '--live-listen' }
    $out = & $py $bindArgs 2>&1
    if ($LASTEXITCODE -eq 3) {
        $msg = ($out | Out-String).Trim()
        if (-not $msg) { $msg = "home $HomePath is owned by another talk seat" }
        Write-Error $msg
    }
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3) {
        Write-Error "talk_seat_pid.py --bind-home failed (exit $LASTEXITCODE): $out"
    }
}
$agent, $listen = Get-HomePythonProcs -HomePath $resolved
$needStart = $true
$agentNick = ''
if ($agent -and ($agent.CommandLine -match '--nick\s+(\S+)')) {
    $agentNick = $Matches[1]
    if ($agentNick -eq $expectedNick) { $needStart = $false }
}
$hasListen = $null -ne $listen
Assert-HomeBind -HomePath $resolved -ExpectedNick $expectedNick -LiveAgentNick $agentNick -LiveListen:$hasListen
if ($needStart) {
    Stop-CursorHomeAgents -HomePath $resolved
    Start-Process -FilePath $py -ArgumentList @(
        '-u', $agentPath,
        '--host', $IrcHost,
        '--port', "$Port",
        '--channel', $Channel,
        '--home', $resolved,
        '--nick', $expectedNick
    ) -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Milliseconds 800
    $agent, $listen = Get-HomePythonProcs -HomePath $resolved
}
if (-not $agent) {
    Write-Error "irc_agent did not start for home $resolved"
}
$agentPid = $agent.ProcessId
$nick = ''
if ($agent.CommandLine -match '--nick\s+(\S+)') { $nick = $Matches[1] }
if ($nick -and $nick -ne $expectedNick) {
    $agentNick = $nick
    $hasListen = $null -ne $listen
    Assert-HomeBind -HomePath $resolved -ExpectedNick $expectedNick -LiveAgentNick $agentNick -LiveListen:$hasListen
    Write-Output "INFO talk-seat nick=$nick expected=$expectedNick - restarting agent"
    Stop-CursorHomeAgents -HomePath $resolved
    Start-Process -FilePath $py -ArgumentList @(
        '-u', $agentPath,
        '--host', $IrcHost,
        '--port', "$Port",
        '--channel', $Channel,
        '--home', $resolved,
        '--nick', $expectedNick
    ) -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Milliseconds 800
    $agent, $listen = Get-HomePythonProcs -HomePath $resolved
    $agentPid = if ($agent) { $agent.ProcessId } else { 0 }
    $nick = $expectedNick
}
if (-not $nick) {
    $nick = $expectedNick
}
$env:AGENTIC_IRC_DEBUG = '1'
& (Join-Path $Scripts 'Start-IrcTsr.ps1') -IrcHome $resolved -Scripts $Scripts -SeatPid $SeatPid -Nick $nick | Out-Null
$listenPid = ''
$agent, $listen = Get-HomePythonProcs -HomePath $resolved
if ($listen) { $listenPid = $listen.ProcessId }
@(
    "nick=$nick"
    "seat=$SeatPid"
    "listen=$listenPid"
    "agent=$agentPid"
    "home=$resolved"
) | Set-Content -LiteralPath (Join-Path $resolved 'coordinator.pid') -Encoding utf8
Write-Output "INFO nick=$nick seat=$SeatPid agent=$agentPid listen=$listenPid home=$resolved"
Write-Output "INFO keep this PowerShell session alive (seat=$SeatPid); listen detached at $(Join-Path $resolved 'listen.stdout.log')"
