# ionos: POST /bob/v1/report via IIS (irc-ntsa) -> loopback bobcallback.py (issue #46 / #73).
#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$IrcRoot,
    [string]$IrcHome,
    [string]$SiteName = 'irc-ntsa',
    [int]$BackendPort = 19781,
    [string]$ReportUrl = 'http://bob.ntsa.uk/bob/v1/report'
)

$ErrorActionPreference = 'Stop'
if (-not $IrcRoot) {
    if (Test-Path 'C:\ai\agentic_irc') { $IrcRoot = 'C:\ai\agentic_irc' }
    else { throw 'IrcRoot not set and C:\ai\agentic_irc missing' }
}
$IrcRoot = [IO.Path]::GetFullPath($IrcRoot)
if (-not $IrcHome) {
    $IrcHome = if ($env:BOB_IRC_HOME) { $env:BOB_IRC_HOME } else { Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
}
$IrcHome = [IO.Path]::GetFullPath($IrcHome)
New-Item -ItemType Directory -Force -Path $IrcHome | Out-Null

$py = 'C:\Python\Python312\python.exe'
if (-not (Test-Path $py)) {
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source } else { throw 'python.exe not found' }
}

$secretDir = Join-Path $env:USERPROFILE '.grok\bob'
New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
$secretPath = Join-Path $secretDir 'report.secret'
if (-not (Test-Path $secretPath)) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes).TrimEnd('=')
    [System.IO.File]::WriteAllText($secretPath, $secret, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Created $secretPath"
}

$logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir 'bobcallback-ionos.log'

Import-Module WebAdministration -ErrorAction Stop
Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name 'enabled' -Value 'True'

$site = Get-Website -Name $SiteName -ErrorAction Stop
$physical = $site.physicalPath
if (-not $physical -or -not (Test-Path $physical)) { throw "Site $SiteName physicalPath missing" }

$webConfigPath = Join-Path $physical 'web.config'
$rewriteBlock = @"
    <rewrite>
      <rules>
        <rule name="BobReportWebhook" stopProcessing="true">
          <match url="^bob/v1/report$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:$BackendPort/bob/v1/report" />
        </rule>
      </rules>
    </rewrite>
"@

if (Test-Path $webConfigPath) {
    [xml]$xml = Get-Content $webConfigPath -Raw
    $sws = $xml.configuration.'system.webServer'
    if (-not $sws) { throw 'web.config missing system.webServer' }
    if ($sws.rewrite) { $sws.RemoveChild($sws.rewrite) | Out-Null }
    $frag = $xml.CreateDocumentFragment()
    $frag.InnerXml = $rewriteBlock.Trim()
    $sws.AppendChild($frag.FirstChild) | Out-Null
    $xml.Save($webConfigPath)
}
else {
    @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
$rewriteBlock
  </system.webServer>
</configuration>
"@ | Set-Content -Path $webConfigPath -Encoding utf8
}

$callback = Join-Path $IrcRoot 'scripts\bobcallback.py'
$running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match 'bobcallback\.py' -and $_.CommandLine -match [regex]::Escape("--port $BackendPort")
})
foreach ($p in $running) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 500

$env:BOB_REPORT_PORT = [string]$BackendPort
[Environment]::SetEnvironmentVariable('BOB_REPORT_PORT', [string]$BackendPort, 'User')
$argList = @(
    '-u', $callback,
    '--home', $IrcHome,
    '--bind', '127.0.0.1',
    '--port', [string]$BackendPort
)
Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $IrcRoot `
    -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError ($logPath + '.err') | Out-Null
Start-Sleep -Seconds 2

$taskName = 'BobReport-ionos'
$wrapper = Join-Path $logDir 'Start-BobReport-ionos.ps1'
@"
`$ErrorActionPreference = 'Stop'
`$py = '$py'
`$callback = '$callback'
`$ircHomeDir = '$IrcHome'
`$log = '$logPath'
`$port = $BackendPort
`$running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    `$_.CommandLine -and `$_.CommandLine -match 'bobcallback\.py' -and `$_.CommandLine -match [regex]::Escape("--port `$port")
})
if (`$running.Count -eq 0) {
    Start-Process -FilePath `$py -ArgumentList @('-u', `$callback, '--home', `$ircHomeDir, '--bind', '127.0.0.1', '--port', [string]`$port) `
        -WorkingDirectory '$IrcRoot' -WindowStyle Hidden -RedirectStandardOutput `$log -RedirectStandardError (`$log + '.err') | Out-Null
}
"@ | Set-Content -Path $wrapper -Encoding utf8

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest | Out-Null

# Local fleet config hint (sister #124 will POST here when landed).
$buildCfg = 'C:\ai\agentic_build\config\bobiverse.json'
if (Test-Path $buildCfg) {
    $cfg = Get-Content $buildCfg -Raw | ConvertFrom-Json
    $cfg | Add-Member -NotePropertyName reportUrl -NotePropertyValue $ReportUrl -Force
    $cfg | ConvertTo-Json -Depth 6 | Set-Content -Path $buildCfg -Encoding utf8
}

Write-Host "reportUrl: $ReportUrl"
Write-Host "backend:   127.0.0.1:$BackendPort (home $IrcHome)"
Write-Host "IIS site:  $SiteName -> $webConfigPath"
Write-Host "secret:    $secretPath"
Write-Host "log:       $logPath"
Write-Host "task:      $taskName"
