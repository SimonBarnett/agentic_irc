# Watch-AgentHealth.ps1 — issue #135 / #144
# Caller polls listen sinks (stdout/tsr/irc.log); agent still initialises IRC (irc_agent).
# Persist Cursor session_id from CLI JSON; resume on wake without full skill reload.
[CmdletBinding()]
param(
    [Alias('grok')]
    [switch]$Grok,
    [Alias('cursor')]
    [switch]$Cursor,
    [string]$Cwd = '',
    [string]$IrcHome = '',
    [string]$Scripts = $PSScriptRoot,
    [string]$RepairScript = '',
    [int]$PollSeconds = 5,
    [int]$IrcStaleSeconds = 900,
    [string]$LogPath = ''
)

$ErrorActionPreference = 'Stop'
if ($Grok -and $Cursor) { throw 'pass only one of -Grok/--grok or -Cursor/--cursor' }
if (-not $Grok -and -not $Cursor) { throw 'required: -Grok/--grok or -Cursor/--cursor' }
$Engine = if ($Grok) { 'grok' } else { 'cursor' }
if (-not $IrcHome) { $IrcHome = Join-Path $env:USERPROFILE '.agentic-irc-cursor' }
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
    param([string[]]$Args)
    $out = & $Py $AgentHealthPy @Args 2>&1
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
    param([string]$Home)
    $coord = Join-Path $Home 'coordinator.pid'
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
    param([string]$Home)
    $json = Invoke-AgentHealthPy -Args @('select-sink', '--home', $Home)
    $doc = $json | ConvertFrom-Json
    return [pscustomobject]@{ Path = $doc.path; Kind = $doc.kind }
}

function Test-IrcTsrHealth {
    param([string]$Home)
    $c = Read-IrcCoordinator -Home $Home
    $agentOk = Test-PidAlive -ProcId $c.agentPid
    $listenOk = Test-PidAlive -ProcId $c.listenPid
    $healthJson = Invoke-AgentHealthPy -Args @(
        'listen-health', '--home', $Home, '--stale-seconds', "$IrcStaleSeconds"
    )
    $h = $healthJson | ConvertFrom-Json
    $logOk = [bool]$h.log_exists
    $stale = [bool]$h.log_stale
    $listenLog = if ($h.listen_log_path) { $h.listen_log_path } else { (Join-Path $Home 'listen.stdout.log') }
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
    param([string]$Home)
    $irc = Test-IrcTsrHealth -Home $Home
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
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tsrScript -IrcHome $Home -Nick $nick -Scripts $Scripts | Out-Null
        return (Test-IrcTsrHealth -Home $Home)
    }
    $roll = Resolve-RepairScript
    if (-not $roll) {
        Write-AgentLog 'IRC repair skipped: no Stop-HungAgent.ps1 and listen/agent still bad'
        return (Test-IrcTsrHealth -Home $Home)
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $roll -IrcHome $Home -Nick $nick -Roll
    return (Test-IrcTsrHealth -Home $Home)
}

function Read-NewIrcFromLines {
    param([string]$Home, [long]$Offset)
    $sink = Get-ListenPollSink -Home $Home
    $json = Invoke-AgentHealthPy -Args @(
        'read-from', '--home', $Home, '--offset', "$Offset", '--sink-path', $sink.Path, '--sink-kind', $sink.Kind
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
    $sid = Invoke-AgentHealthPy -Args @('parse-cursor-session', '--file', $Path)
    if ($sid -eq 'null' -or -not $sid) { return $null }
    return $sid.Trim()
}

function Ensure-AgentSession {
    param($AgentInfo, [string]$SessionPath, [string]$WorkDir)
    $id = Read-SavedSessionId -Path $SessionPath
    if ($AgentInfo.Engine -eq 'cursor') {
        $bound = Invoke-AgentHealthPy -Args @('cursor-bound', '--session-path', $SessionPath)
        if ($bound -eq 'true') {
            Write-AgentLog ("session exists id={0}" -f $id)
            return $id
        }
    }
    elseif ($id) {
        Write-AgentLog ("session exists id={0}" -f $id)
        return $id
    }

    $boot = @"
You are a fleet talk/build seat. Load irc + build skills; CAST IRON harvest.
IRC connection is initialised by the IRC TSR (irc_agent); this caller will trigger you when new IRC FROM lines arrive - do not busy-poll IRC yourself.
Do not stamp UAT. Do not push main.
"@
    if ($AgentInfo.Engine -eq 'grok') {
        $id = [guid]::NewGuid().ToString()
        Save-SessionId -Path $SessionPath -Id $id
        Write-AgentLog ("boot grok session={0}" -f $id)
        $p = Start-Process -FilePath $AgentInfo.Path -ArgumentList @(
            '--cwd', $WorkDir, '--always-approve', '--session-id', $id, '-p', $boot
        ) -WorkingDirectory $WorkDir -PassThru -WindowStyle Hidden
        Wait-Process -Id $p.Id -Timeout 180 -ErrorAction SilentlyContinue
        return (Read-SavedSessionId -Path $SessionPath)
    }

    $exe = Resolve-CursorAgentExe -AgentInfo $AgentInfo
    $outFile = Join-Path $env:TEMP ("watch-agent-boot-{0}.jsonl" -f $PID)
    Write-AgentLog 'boot cursor session (await CLI session_id)'
    $p = Start-Process -FilePath $exe -ArgumentList @(
        '--cwd', $WorkDir, '--force', '--trust', '--print', '--output-format', 'json', $boot
    ) -WorkingDirectory $WorkDir -PassThru -WindowStyle Hidden -RedirectStandardOutput $outFile -RedirectStandardError (Join-Path $env:TEMP ("watch-agent-boot-{0}.err" -f $PID))
    Wait-Process -Id $p.Id -Timeout 600 -ErrorAction SilentlyContinue
    $sid = Parse-CursorSessionFromFile -Path $outFile
    if (-not $sid) {
        Write-AgentLog 'boot cursor failed: no session_id in CLI output'
        return $null
    }
    Invoke-AgentHealthPy -Args @('mark-cursor-bound', '--session-path', $SessionPath, '--session-id', $sid) | Out-Null
    Write-AgentLog ("boot cursor bound session_id={0}" -f $sid)
    return $sid
}

function Invoke-AgentOnIrcTraffic {
    param($AgentInfo, [string]$SessionId, [string]$WorkDir, [string[]]$FromLines, [string]$SinkPath)
    if (-not $FromLines -or $FromLines.Count -eq 0) { return $false }
    $sinkName = Split-Path -Leaf $SinkPath
    $payload = Invoke-AgentHealthPy -Args @(
        'format-wake', '--sink-name', $sinkName, '--lines', ($FromLines -join "`n")
    )
    Write-AgentLog ("trigger Agent TSR lines={0} session={1}" -f $FromLines.Count, $SessionId)
    $started = $false
    $code = $null
    if ($AgentInfo.Engine -eq 'grok') {
        $args = @('--cwd', $WorkDir, '--always-approve', '-p', $payload)
        if ($SessionId) { $args = @('--cwd', $WorkDir, '--always-approve', '--resume', $SessionId, '-p', $payload) }
        $proc = Start-Process -FilePath $AgentInfo.Path -ArgumentList $args -WorkingDirectory $WorkDir -PassThru -WindowStyle Normal
        $started = $true
    }
    else {
        $exe = Resolve-CursorAgentExe -AgentInfo $AgentInfo
        $promptFile = Join-Path $env:TEMP ('watch-agent-wake-{0}-{1}.txt' -f $PID, [DateTime]::UtcNow.Ticks)
        [IO.File]::WriteAllText($promptFile, $payload, [Text.UTF8Encoding]::new($false))
        $outFile = Join-Path $env:TEMP ('watch-agent-wake-{0}-{1}.jsonl' -f $PID, [DateTime]::UtcNow.Ticks)
        if ($SessionId) {
            $proc = Start-Process -FilePath $exe -ArgumentList @(
                '--cwd', $WorkDir, '--force', '--trust', '--resume', $SessionId,
                '--print', '--output-format', 'json', $payload
            ) -WorkingDirectory $WorkDir -PassThru -WindowStyle Normal -RedirectStandardOutput $outFile
        }
        else {
            $proc = Start-Process -FilePath $exe -ArgumentList @(
                '--cwd', $WorkDir, '--force', '--trust', '--print', '--output-format', 'json', $payload
            ) -WorkingDirectory $WorkDir -PassThru -WindowStyle Normal -RedirectStandardOutput $outFile
        }
        $started = $true
    }
    if ($started) {
        Write-AgentLog ("Agent TSR started pid={0}" -f $proc.Id)
        Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
        try { $code = $proc.ExitCode } catch { }
        Write-AgentLog ("Agent TSR exited pid={0} code={1}" -f $proc.Id, $code)
    }
    if (-not $started) { return $false }
    if ($null -ne $code -and $code -ne 0) { return $false }
    return $true
}

# --- main ---
if (-not $LogPath) {
    $logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $LogPath = Join-Path $logDir 'watch-agent-health.log'
}
$script:LogPath = $LogPath
if (-not (Test-Path -LiteralPath $Cwd)) { throw "Cwd missing: $Cwd" }
New-Item -ItemType Directory -Force -Path $IrcHome | Out-Null

$agent = Resolve-AgentExe -Want $Engine
$sessionPath = Get-SessionStorePath -Eng $Engine
Write-AgentLog ("engine={0} path={1} cwd={2} ircHome={3} scripts={4}" -f $agent.Engine, $agent.Path, $Cwd, $IrcHome, $Scripts)

[void](Ensure-IrcTsr -Home $IrcHome)

$sessionId = Ensure-AgentSession -AgentInfo $agent -SessionPath $sessionPath -WorkDir $Cwd

$listenOffset = 0L
$initialSink = Get-ListenPollSink -Home $IrcHome
if (Test-Path -LiteralPath $initialSink.Path) { $listenOffset = (Get-Item $initialSink.Path).Length }

Write-AgentLog 'caller loop: poll IRC; trigger agent on new FROM lines'
while ($true) {
    $irc = Test-IrcTsrHealth -Home $IrcHome
    if (-not $irc.Healthy) {
        Write-AgentLog 'IRC TSR failed health check - repairing'
        [void](Ensure-IrcTsr -Home $IrcHome)
    }

    $read = Read-NewIrcFromLines -Home $IrcHome -Offset $listenOffset
    if ($read.Lines.Count -gt 0) {
        $delivered = Invoke-AgentOnIrcTraffic -AgentInfo $agent -SessionId $sessionId -WorkDir $Cwd -FromLines $read.Lines -SinkPath $read.SinkPath
        if ($delivered) {
            $listenOffset = $read.NextOffset
        }
        else {
            Write-AgentLog 'Agent TSR delivery failed; keeping listen offset for replay'
        }
        $sessionId = Read-SavedSessionId -Path $sessionPath
    }

    Start-Sleep -Seconds $PollSeconds
}
