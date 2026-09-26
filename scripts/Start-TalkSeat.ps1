# Start or reuse irc_agent + irc_listen for a talk seat.
# Nick = {machine-id}-{irc_agent PID} (never irc_listen / PowerShell $PID).
# Fresh homes: start with --auto-nick (AGENTIC_IRC_SEAT_PID=self); never empty --nick.
# Detached irc_listen via Start-IrcTsr.ps1; tail $IrcHome/listen.stdout.log for wakes.
# FR #237: first bind/start must not use uninitialised $expectedNick.
param(
    [Parameter(Mandatory = $true)]
    [string]$MachineId,
    [string]$IrcHome = $(Join-Path $env:USERPROFILE '.agentic-irc-cursor'),
    [string]$Scripts = $PSScriptRoot,
    [string]$IrcHost = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Channel = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $Scripts 'IrcProcess.ps1')
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
$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (-not (Test-Path -LiteralPath $pwFile)) {
    Write-Error "missing connect.password at $pwFile"
}
$env:AGENTIC_IRC_PASSWORD = (Get-Content -LiteralPath $pwFile -Raw).Trim()
$env:AGENTIC_IRC_DEBUG = '1'
$env:AGENTIC_IRC_SEAT_PID = 'self'
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
    if (-not $ExpectedNick) {
        Write-Error "Assert-HomeBind requires a non-empty ExpectedNick (FR #237)"
    }
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

function Start-OneSeatAgent {
    param(
        [string]$NickToStart,
        [switch]$AutoNick
    )
    if (-not $NickToStart) {
        Write-Error "Start-OneSeatAgent refuses empty --nick (FR #237)"
    }
    $prior = Join-Path $Scripts 'prior_irc.py'
    Invoke-PriorIrcClean -Python $py -ScriptPath $prior -Nick $NickToStart -Home $resolved
    $argList = @(
        '-u', $agentPath,
        '--host', $IrcHost,
        '--port', "$Port",
        '--channel', $Channel,
        '--home', $resolved,
        '--nick', $NickToStart
    )
    if ($AutoNick) {
        $argList += '--auto-nick'
    }
    $null = Start-HiddenPython -Python $py -ArgumentList $argList -WorkingDirectory $Scripts
}

function Get-CoordNick {
    param([string]$HomePath)
    $coordPath = Join-Path $HomePath 'coordinator.pid'
    if (-not (Test-Path -LiteralPath $coordPath)) { return '' }
    foreach ($line in Get-Content -LiteralPath $coordPath) {
        if ($line -match '^nick=(.+)$') { return $Matches[1].Trim() }
    }
    return ''
}

# --- resolve live processes on this home only ---
$agent, $listen = Get-HomePythonProcs -HomePath $resolved
$agentNick = ''
if ($agent -and ($agent.CommandLine -match '--nick\s+(\S+)')) {
    $agentNick = $Matches[1]
}
$hasListen = $null -ne $listen
$coordNick = Get-CoordNick -HomePath $resolved

# Refuse stealing another seat's occupied home (need a concrete expected nick).
# Fresh empty home: no agent, no listen, no foreign coord → proceed to auto-nick start.
if ($agentNick -or $hasListen -or $coordNick) {
    $probeExpected = $agentNick
    if (-not $probeExpected -and $coordNick) { $probeExpected = $coordNick }
    if (-not $probeExpected) {
        # Occupied listen without nick: still refuse empty bind — use machine placeholder
        # only for the refusal check against foreign coordinator.pid.
        $probeExpected = "$mid-0"
    }
    # If live agent nick is already a valid {mid}-{pid} matching its PID, reuse path below.
    $reuseOk = $false
    if ($agent -and $agentNick) {
        $want = "$mid-$($agent.ProcessId)"
        if ($agentNick -eq $want) { $reuseOk = $true }
    }
    if (-not $reuseOk) {
        Assert-HomeBind -HomePath $resolved -ExpectedNick $probeExpected `
            -LiveAgentNick $agentNick -LiveListen:$hasListen
    }
}

$needStart = $true
if ($agent -and $agentNick) {
    $want = "$mid-$($agent.ProcessId)"
    if ($agentNick -eq $want) { $needStart = $false }
}

if ($needStart) {
    Stop-CursorHomeAgents -HomePath $resolved
    # Fresh / reclaim: --auto-nick rewrites {mid}-0 → {mid}-{irc_agent PID}
    Start-OneSeatAgent -NickToStart "$mid-0" -AutoNick
    Start-Sleep -Milliseconds 800
    $agent, $listen = Get-HomePythonProcs -HomePath $resolved
}

if (-not $agent) {
    Write-Error "irc_agent did not start for home $resolved"
}

$agentPid = $agent.ProcessId
$expectedNick = "$mid-$agentPid"
$nick = ''
if ($agent.CommandLine -match '--nick\s+(\S+)') { $nick = $Matches[1] }

# auto-nick should already match; if not, restart once with the concrete nick.
if ($nick -and $nick -ne $expectedNick) {
    $agentNick = $nick
    $hasListen = $null -ne $listen
    Assert-HomeBind -HomePath $resolved -ExpectedNick $expectedNick `
        -LiveAgentNick $agentNick -LiveListen:$hasListen
    Write-Output "INFO talk-seat nick=$nick expected=$expectedNick - restarting agent"
    Stop-CursorHomeAgents -HomePath $resolved
    Start-OneSeatAgent -NickToStart $expectedNick
    Start-Sleep -Milliseconds 800
    $agent, $listen = Get-HomePythonProcs -HomePath $resolved
    if (-not $agent) {
        Write-Error "irc_agent did not restart for home $resolved"
    }
    $agentPid = $agent.ProcessId
    $expectedNick = "$mid-$agentPid"
    $nick = $expectedNick
}
if (-not $nick) {
    $nick = $expectedNick
}
if (-not $nick) {
    Write-Error "talk-seat nick is empty after start (FR #237)"
}

$env:AGENTIC_IRC_DEBUG = '1'
if (-not $needStart -and $agent) {
    # Keep this seat's agent. Drop same-nick twins and hung listens on this home.
    Invoke-PriorIrcClean -Python $py -ScriptPath (Join-Path $Scripts 'prior_irc.py') `
        -Nick $expectedNick -Home $resolved -KeepPid ([int]$agent.ProcessId)
}
& (Join-Path $Scripts 'Start-IrcTsr.ps1') -IrcHome $resolved -Scripts $Scripts -SeatPid $SeatPid -Nick $nick | Out-Null
$listenPid = ''
$agent, $listen = Get-HomePythonProcs -HomePath $resolved
if ($listen) { $listenPid = $listen.ProcessId }
if ($agent) { $agentPid = $agent.ProcessId; $expectedNick = "$mid-$agentPid"; if (-not $nick) { $nick = $expectedNick } }
@(
    "nick=$nick"
    "seat=$agentPid"
    "listen=$listenPid"
    "agent=$agentPid"
    "home=$resolved"
) | Set-Content -LiteralPath (Join-Path $resolved 'coordinator.pid') -Encoding utf8
Write-Output "INFO nick=$nick agent=$agentPid listen=$listenPid home=$resolved"
Write-Output "INFO listen detached at $(Join-Path $resolved 'listen.stdout.log')"
