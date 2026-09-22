# Redacted NAMES probe for fleet channels (no password in output).
param(
    [string]$IrcHost = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [string[]]$Channels = @('#bobiverse', '#flamingo', '#agentic_irc')
)
$ErrorActionPreference = 'Stop'
$pwFile = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
if (-not (Test-Path -LiteralPath $pwFile)) { Write-Error "missing connect.password" }
$pass = (Get-Content -LiteralPath $pwFile -Raw).Trim()
$nick = 'names-probe-' + (Get-Random -Maximum 999999)
$tcp = New-Object System.Net.Sockets.TcpClient
$tcp.Connect($IrcHost, $Port)
$ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, ({ $true }))
$ssl.AuthenticateAsClient($IrcHost)
$w = New-Object System.IO.StreamWriter($ssl)
$w.NewLine = "`r`n"
$w.AutoFlush = $true
$r = New-Object System.IO.StreamReader($ssl)
$w.WriteLine("PASS $pass")
$w.WriteLine('CAP END')
$w.WriteLine("NICK $nick")
$w.WriteLine("USER $nick 0 * :names-probe")
Start-Sleep -Seconds 2
while ($tcp.Available -gt 0) {
    $line = $r.ReadLine()
    if ($line -match '^PING ') { $w.WriteLine('PONG ' + $line.Substring(5)) }
}
foreach ($ch in $Channels) {
    $w.WriteLine("NAMES $ch")
    Start-Sleep -Seconds 1
}
Start-Sleep -Seconds 2
$blob = ''
while ($tcp.Available -gt 0) { $blob += $r.ReadLine() + "`n" }
$tcp.Close()
$redacted = $blob -replace 'flamingo-\d+', 'flamingo-REDACTED'
$redacted = $redacted -replace 'deadtcp-\d+', 'deadtcp-REDACTED'
$redacted = $redacted -replace 'halfopen-\d+', 'halfopen-REDACTED'
$redacted = $redacted -replace 'names-probe-\d+', 'names-probe-REDACTED'
Write-Output "INFO probe at $(Get-Date -Format o)"
Write-Output $redacted
