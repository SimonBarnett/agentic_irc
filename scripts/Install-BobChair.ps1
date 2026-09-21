# Digest chair seat on ionos: #bobiverse only, !bobiverse + webhook digest (issue #73).
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$agent = Join-Path $here 'irc_agent.py'
# Digest file lives on the briefer box home (#73), not the Cursor coordinator home.
$ircHome = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
if ($env:BOB_IRC_HOME -and $env:BOB_IRC_HOME.Trim()) { $ircHome = $env:BOB_IRC_HOME.Trim() }
$nick = if ($env:AGENTIC_IRC_CHAIR_NICK) { $env:AGENTIC_IRC_CHAIR_NICK.Trim() } else { 'Jeeves' }
$env:AGENTIC_IRC_CHAIR_NICK = $nick
$py = 'C:\Python\Python312\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (Test-Path $pwFile) { $env:AGENTIC_IRC_PASSWORD = (Get-Content $pwFile -Raw).Trim() }
$env:AGENTIC_IRC_DEBUG = '1'
$env:AGENTIC_IRC_HOME = $ircHome
$running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match 'irc_agent\.py' -and $_.CommandLine -match [regex]::Escape($nick) -and $_.CommandLine -match '--chair'
})
if ($running.Count -eq 0) {
    Start-Process -FilePath $py -ArgumentList @(
        '-u', $agent, '--host', 'irc.ntsa.uk', '--port', '6697',
        '--nick', $nick, '--channel', '#bobiverse', '--home', $ircHome, '--chair', '--announce-key', '--hello', 'digest-chair'
    ) -WorkingDirectory (Split-Path $here -Parent) -WindowStyle Hidden | Out-Null
}
Write-Host "Chair: nick=$nick home=$ircHome"
