# Watch-AgentHealth.ps1 — issue #135 / #144
# Caller polls listen sinks (stdout/tsr/irc.log); agent still initialises IRC (irc_agent).
# Persist Cursor session_id from CLI JSON; resume on wake without full skill reload.
# -Aider wakes a live aider.exe REPL via console WriteConsoleInput / SendKeys (not --message).
[CmdletBinding()]
param(
    # Aliases omitted: PS 5.1 rejects same-name alias on switch params (case-insensitive name clash).
    # -Grok/-Cursor/-Aider already bind case-insensitively as -grok/-cursor/-aider.
    [switch]$Grok,
    [switch]$Cursor,
    [switch]$Aider,
    [int]$AiderPid = 0,
    [string]$Cwd = '',
    [string]$IrcHome = '',
    [string]$Scripts = $PSScriptRoot,
    [string]$RepairScript = '',
    [int]$PollSeconds = 5,
    [int]$IrcStaleSeconds = 900,
    [string]$LogPath = ''
)

$ErrorActionPreference = 'Stop'
$nModes = 0
if ($Grok) { $nModes++ }
if ($Cursor) { $nModes++ }
if ($Aider) { $nModes++ }
if ($nModes -gt 1) { throw 'pass only one of -Grok/--grok, -Cursor/--cursor, or -Aider/--aider' }
if ($nModes -lt 1) { throw 'required: -Grok/--grok, -Cursor/--cursor, or -Aider/--aider' }
$Engine = if ($Grok) { 'grok' } elseif ($Cursor) { 'cursor' } else { 'aider' }
if (-not $IrcHome) {
    if ($Engine -eq 'aider') { $IrcHome = Join-Path $env:USERPROFILE '.agentic-irc-aider' }
    else { $IrcHome = Join-Path $env:USERPROFILE '.agentic-irc-cursor' }
}
if (-not $Cwd) {
    $parent = Split-Path $Scripts -Parent
    if (Test-Path -LiteralPath (Join-Path $parent 'scripts\irc_agent.py')) { $Cwd = $parent }
    elseif (Test-Path -LiteralPath 'C:\ai\agentic_irc') { $Cwd = 'C:\ai\agentic_irc' }
    else { $Cwd = 'C:\ai\agentic_build' }
}

$AgentHealthPy = Join-Path $Scripts 'agent_health.py'
$Py = (Get-Command python -ErrorAction Stop).Source

function Write-AgentLog {
    param([string]$Message)
    $line = '{0:yyyy-MM-ddTHH:mm:ssZ} {1}' -f (Get-Date).ToUniversalTime(), $Message
    Write-Host $line
    if ($script:LogPath) {
        [IO.File]::AppendAllText($script:LogPath, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    }
}

function Invoke-AgentHealthPy {
    param([string[]]$PyArgs)
    $out = & $Py $AgentHealthPy @PyArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "agent_health.py failed ($LASTEXITCODE): $out"
    }
    return ($out | Out-String).Trim()
}

function Resolve-AgentExe {
    param([string]$Want)
    $grok = Join-Path $env:USERPROFILE '.grok\bin\agent.exe'
    $cursorCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.cmd'),
        (Join-Path $env:LOCALAPPDATA 'cursor-agent\cursor-agent.cmd'),
        (Join-Path $env:USERPROFILE '.local\bin\cursor-agent.exe')
    )
    $cursor = $cursorCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($Want -eq 'grok') {
        if (-not (Test-Path -LiteralPath $grok)) { throw "grok agent not found: $grok" }
        return [pscustomobject]@{ Engine = 'grok'; Path = $grok }
    }
    if ($Want -eq 'aider') {
        $aiderCandidates = @(
            (Join-Path $env:USERPROFILE 'venvs\aider\Scripts\aider.exe'),
            (Join-Path 'D:\Users\Administrator\venvs\aider\Scripts' 'aider.exe'),
            (Join-Path $env:USERPROFILE 'AppData\Roaming\Python\Python312\Scripts\aider.exe')
        )
        $cmd = Get-Command aider.exe -ErrorAction SilentlyContinue
        if ($cmd) { $aiderCandidates = @($cmd.Source) + $aiderCandidates }
        $aider = $aiderCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
        if (-not $aider) { throw 'aider.exe not found (venv Scripts or PATH). Start live REPL first; watcher does not --message one-shot.' }
        return [pscustomobject]@{ Engine = 'aider'; Path = $aider }
    }
    if (-not $cursor) { throw 'cursor agent.cmd not found under LocalAppData\cursor-agent' }
    return [pscustomobject]@{ Engine = 'cursor'; Path = $cursor }
}

function Get-SessionStorePath {
    param([string]$Eng)
    $dir = Join-Path $env:USERPROFILE '.grok\bob-bridge'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return (Join-Path $dir ("watch-agent-health-{0}.session" -f $Eng))
}

function Read-SavedSessionId {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $raw = (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue)
    if (-not $raw) { return $null }
    $t = $raw.Trim()
    if ($t) { return $t }
    return $null
}

function Save-SessionId {
    param([string]$Path, [string]$Id)
    if (-not $Id) { return }
    [IO.File]::WriteAllText($Path, $Id.Trim() + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-AgentLog ("session saved id={0}" -f $Id)
}

function Read-IrcCoordinator {
    param([string]$SeatHome)
    $coord = Join-Path $SeatHome 'coordinator.pid'
    $out = [ordered]@{ path = $coord; nick = ''; seat = ''; agentPid = 0; listenPid = 0 }
    if (-not (Test-Path -LiteralPath $coord)) { return [pscustomobject]$out }
    Get-Content -LiteralPath $coord -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_ -match '^nick=(.+)$') { $out.nick = $Matches[1].Trim() }
        elseif ($_ -match '^seat=(.+)$') { $out.seat = $Matches[1].Trim() }
        elseif ($_ -match '^agent=(\d+)$') { $out.agentPid = [int]$Matches[1] }
        elseif ($_ -match '^listen=(\d+)$') { $out.listenPid = [int]$Matches[1] }
    }
    return [pscustomobject]$out
}

function Test-PidAlive {
    param([int]$ProcId)
    if ($ProcId -le 0) { return $false }
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

function Get-ListenPollSink {
    param([string]$SeatHome)
    $json = Invoke-AgentHealthPy -PyArgs @('select-sink', '--home', $SeatHome)
    $doc = $json | ConvertFrom-Json
    return [pscustomobject]@{ Path = $doc.path; Kind = $doc.kind }
}

function Test-IrcTsrHealth {
    param([string]$SeatHome)
    $c = Read-IrcCoordinator -SeatHome $SeatHome
    $agentOk = Test-PidAlive -ProcId $c.agentPid
    $listenOk = Test-PidAlive -ProcId $c.listenPid
    $healthJson = Invoke-AgentHealthPy -PyArgs @(
        'listen-health', '--home', $SeatHome, '--stale-seconds', "$IrcStaleSeconds"
    )
    $h = $healthJson | ConvertFrom-Json
    $logOk = [bool]$h.log_exists
    $stale = [bool]$h.log_stale
    $listenLog = if ($h.listen_log_path) { $h.listen_log_path } else { (Join-Path $SeatHome 'listen.stdout.log') }
    return [pscustomobject]@{
        Coordinator = $c
        AgentOk     = $agentOk
        ListenOk    = $listenOk
        LogOk       = $logOk
        Stale       = $stale
        ListenLog   = $listenLog
        Healthy     = ($agentOk -and $listenOk -and $logOk -and -not $stale)
    }
}

function Resolve-RepairScript {
    if ($RepairScript -and (Test-Path -LiteralPath $RepairScript)) { return $RepairScript }
    $candidates = @(
        (Join-Path (Split-Path $Scripts -Parent) 'agentic_build\tools\Stop-HungAgent.ps1'),
        'C:\ai\agentic_build\tools\Stop-HungAgent.ps1'
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

function Ensure-IrcTsr {
    param([string]$SeatHome)
    $irc = Test-IrcTsrHealth -SeatHome $SeatHome
    if ($irc.Healthy) {
        Write-AgentLog ("IRC TSR ok nick={0} agent={1} listen={2} log={3}" -f $irc.Coordinator.nick, $irc.Coordinator.agentPid, $irc.Coordinator.listenPid, $irc.ListenLog)
        return $irc
    }
    Write-AgentLog ("IRC TSR unhealthy agentOk={0} listenOk={1} logOk={2} stale={3} - repairing" -f $irc.AgentOk, $irc.ListenOk, $irc.LogOk, $irc.Stale)
    $nick = $irc.Coordinator.nick
    if (-not $nick) {
        $mach = $env:COMPUTERNAME
        if ($mach -match 'dev1') { $nick = "ce-priority-dev1-$PID" }
        else { $nick = ("{0}-{1}" -f $mach.ToLowerInvariant(), $PID) }
        Write-AgentLog ("IRC TSR no nick in coordinator; using {0}" -f $nick)
    }
    $tsrScript = Join-Path $Scripts 'Start-IrcTsr.ps1'
    if ($irc.AgentOk -and -not $irc.ListenOk -and (Test-Path -LiteralPath $tsrScript)) {
        Write-AgentLog 'IRC repair: Start-IrcTsr (listen only)'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tsrScript -IrcHome $SeatHome -Nick $nick -Scripts $Scripts | Out-Null
        return (Test-IrcTsrHealth -SeatHome $SeatHome)
    }
    $roll = Resolve-RepairScript
    if (-not $roll) {
        Write-AgentLog 'IRC repair skipped: no Stop-HungAgent.ps1 and listen/agent still bad'
        return (Test-IrcTsrHealth -SeatHome $SeatHome)
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $roll -IrcHome $SeatHome -Nick $nick -Roll
    return (Test-IrcTsrHealth -SeatHome $SeatHome)
}

function Read-NewIrcFromLines {
    param([string]$SeatHome, [long]$Offset)
    $sink = Get-ListenPollSink -SeatHome $SeatHome
    $json = Invoke-AgentHealthPy -PyArgs @(
        'read-from', '--home', $SeatHome, '--offset', "$Offset", '--sink-path', $sink.Path, '--sink-kind', $sink.Kind
    )
    $doc = $json | ConvertFrom-Json
    return [pscustomobject]@{
        Lines      = @($doc.lines)
        NextOffset = [long]$doc.next_offset
        SinkPath   = $sink.Path
        SinkKind   = $sink.Kind
    }
}

function Resolve-CursorAgentExe {
    param($AgentInfo)
    $ps1 = Join-Path (Split-Path $AgentInfo.Path) 'cursor-agent.ps1'
    if (-not (Test-Path $ps1)) { $ps1 = Join-Path (Split-Path $AgentInfo.Path) 'agent.ps1' }
    if (Test-Path $ps1) { return $ps1 }
    return $AgentInfo.Path
}

function Parse-CursorSessionFromFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $sid = Invoke-AgentHealthPy -PyArgs @('parse-cursor-session', '--file', $Path)
    if ($sid -eq 'null' -or -not $sid) { return $null }
    return $sid.Trim()
}


function Find-LiveAiderProcess {
    param([int]$PreferPid = 0)
    if ($PreferPid -gt 0) {
        $p = Get-Process -Id $PreferPid -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -match '^(aider|python)$') { return $p }
        throw "AiderPid=$PreferPid not a live aider/python process"
    }
# STAGED_PARTIAL_9000_OF_24878
