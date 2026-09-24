# Measure seconds until a nick leaves #bobiverse NAMES after abrupt TCP close (no QUIT).
param(
    [string]$IrcHost = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string]$Channel = '#bobiverse',
    [int]$PollSec = 10,
    [int]$MaxWaitSec = 300
)
$ErrorActionPreference = 'Stop'
$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (-not (Test-Path -LiteralPath $pwFile)) { Write-Error "missing connect.password" }
$pass = (Get-Content -LiteralPath $pwFile -Raw).Trim()

function New-IrcSession($nick) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect($IrcHost, $Port)
    $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, ({ $true }))
    $ssl.AuthenticateAsClient($IrcHost)
    $w = New-Object System.IO.StreamWriter($ssl)
    $w.NewLine = "`r`n"
    $w.AutoFlush = $true
    $r = New-Object System.IO.StreamReader($ssl)
    $w.WriteLine("PASS $pass")
    $w.WriteLine('CAP LS 302')
    Start-Sleep -Milliseconds 900
    while ($tcp.Available -gt 0) { $r.ReadLine() | Out-Null }
    $w.WriteLine('CAP END')
    $w.WriteLine("NICK $nick")
    $w.WriteLine("USER $nick 0 * :deadtcp-measure")
    Start-Sleep -Seconds 2
    $got001 = $false
    while ($tcp.Available -gt 0) {
        $line = $r.ReadLine()
        if ($line -match ' 001 ') { $got001 = $true }
        if ($line -match '^PING ') { $w.WriteLine('PONG ' + $line.Substring(5)) }
    }
    if (-not $got001) { throw "no 001 for $nick" }
    return @{ Tcp = $tcp; Ssl = $ssl; W = $w; R = $r }
}

$nick = 'deadtcp-' + (Get-Random -Maximum 999999)
$s = New-IrcSession $nick
$s.W.WriteLine("JOIN $Channel")
Start-Sleep -Seconds 2
while ($s.Tcp.Available -gt 0) {
    $line = $s.R.ReadLine()
    if ($line -match '^PING ') { $s.W.WriteLine('PONG ' + $line.Substring(5)) }
}
$killAt = Get-Date
$s.Tcp.Client.Close()
Write-Output "INFO abrupt-close nick=$nick at $($killAt.ToString('o'))"

$gone = $false
$elapsed = 0
for ($t = 0; $t -le $MaxWaitSec; $t += $PollSec) {
    Start-Sleep -Seconds $PollSec
    $elapsed = $t + $PollSec
    $obs = 'deadtcp-obs-' + (Get-Random -Maximum 999999)
    try {
        $o = New-IrcSession $obs
        $o.W.WriteLine("NAMES $Channel")
        Start-Sleep -Seconds 2
        $blob = ''
        while ($o.Tcp.Available -gt 0) { $blob += ' ' + $o.R.ReadLine() }
        $o.Tcp.Close()
        if ($blob -notmatch "\s$nick\s" -and $blob -notmatch ":$nick\s") {
            $gone = $true
            break
        }
    } catch {
        Write-Output "WARN poll failed: $_"
    }
}
Write-Output "RESULT nick=$nick gone=$gone elapsed_sec=$elapsed host=$IrcHost channel=$Channel"
