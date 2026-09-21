# Start or reuse irc_agent + irc_listen for a talk seat.
# Nick = {machine-id}-{SeatPid} where SeatPid is this PowerShell session $PID (not python children).
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
    $Channel = "#bobiverse,#$mid"
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
function Stop-CursorHomeAgents {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -match 'irc_(agent|listen)\.py' -and
            $_.CommandLine -match [regex]::Escape($resolved)
        } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 400
}
$agent = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'irc_agent.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
    Select-Object -First 1
$needStart = $true
if ($agent -and ($agent.CommandLine -match '--nick\s+(\S+)')) {
    if ($Matches[1] -eq $expectedNick) { $needStart = $false }
}
if ($needStart) {
    Stop-CursorHomeAgents
    Start-Process -FilePath $py -ArgumentList @(
        '-u', $agentPath,
        '--host', $IrcHost,
        '--port', "$Port",
        '--channel', $Channel,
        '--home', $resolved,
        '--nick', $expectedNick
    ) -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Milliseconds 800
    $agent = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'irc_agent.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
        Select-Object -First 1
}
if (-not $agent) {
    Write-Error "irc_agent did not start for home $resolved"
}
$agentPid = $agent.ProcessId
$nick = ''
if ($agent.CommandLine -match '--nick\s+(\S+)') { $nick = $Matches[1] }
if ($nick -and $nick -ne $expectedNick) {
    Write-Output "INFO talk-seat nick=$nick expected=$expectedNick - restarting agent"
    Stop-CursorHomeAgents
    Start-Process -FilePath $py -ArgumentList @(
        '-u', $agentPath,
        '--host', $IrcHost,
        '--port', "$Port",
        '--channel', $Channel,
        '--home', $resolved,
        '--nick', $expectedNick
    ) -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Milliseconds 800
    $agent = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'irc_agent.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
        Select-Object -First 1
    $agentPid = if ($agent) { $agent.ProcessId } else { 0 }
    $nick = $expectedNick
}
if (-not $nick) {
    $nick = $expectedNick
}
$env:AGENTIC_IRC_DEBUG = '1'
& (Join-Path $Scripts 'Start-IrcTsr.ps1') -IrcHome $resolved -Scripts $Scripts -SeatPid $SeatPid -Nick $nick | Out-Null
$listenPid = ''
$listen = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'irc_listen.py' -and $_.CommandLine -match [regex]::Escape($resolved) } |
    Select-Object -First 1
if ($listen) { $listenPid = $listen.ProcessId }
@(
    "nick=$nick"
    "seat=$SeatPid"
    "listen=$listenPid"
    "agent=$agentPid"
    "home=$resolved"
) | Set-Content -LiteralPath (Join-Path $resolved 'coordinator.pid') -Encoding utf8
Write-Output "INFO nick=$nick seat=$SeatPid agent=$agentPid listen=$listenPid home=$resolved"
