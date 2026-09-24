#requires -Version 5.1
<#
.SYNOPSIS
  Every 2 minutes, POST this box's xAI weekly + Cursor meters to the digest webhook (#174).
.DESCRIPTION
  Long-running. Uses BobBridge Get-BobWeeklyRemaining / Get-BobCursorAgentWeeklyRemaining
  when available. Lesser remaining across machines is enforced server-side on merge.
.PARAMETER IntervalSeconds
  Default 120.
.PARAMETER Once
  Single POST then exit (for tests / dry ops).
.PARAMETER DryRun
  Print payload JSON; do not POST.
#>
[CmdletBinding()]
param(
    [int]$IntervalSeconds = 120,
    [switch]$Once,
    [switch]$DryRun,
    [string]$Machine = '',
    [string]$ReportUrl = ''
)

$ErrorActionPreference = 'Continue'

function Resolve-BobBridgeRoot {
    foreach ($root in @('C:\ai\agentic_build', 'D:\ai\agentic_build', 'C:\src\agentic_build')) {
        $psd = Join-Path $root 'src\BobBridge.psd1'
        if (Test-Path $psd) { return $root }
    }
    return $null
}

function Resolve-MachineId {
    param([string]$Hint)
    if ($Hint) { return $Hint.Trim().ToLowerInvariant() }
    if ($env:AGENTIC_IRC_MACHINE) { return $env:AGENTIC_IRC_MACHINE.Trim().ToLowerInvariant() }
    $hn = $env:COMPUTERNAME
    if (-not $hn) { return 'unknown' }
    $low = $hn.ToLowerInvariant()
    if ($low -match 'flamingo') { return 'flamingo' }
    if ($low -match 'marchhare') { return 'marchhare' }
    if ($low -match 'ionos') { return 'ionos' }
    if ($low -match 'ce-priority|dev1') { return 'ce-priority-dev1' }
    return $low
}

function Get-MetricsPayload {
    param([string]$MachineId)
    $payload = [ordered]@{
        op      = 'merge'
        machine = $MachineId
        online  = $true
    }
    $root = Resolve-BobBridgeRoot
    if ($root) {
        Import-Module (Join-Path $root 'src\BobBridge.psd1') -Force -ErrorAction SilentlyContinue
        try {
            if (Get-Command Get-BobWeeklyRemaining -ErrorAction SilentlyContinue) {
                $w = Get-BobWeeklyRemaining
                if ($null -ne $w.remaining_pct) { $payload['weekly'] = [int]$w.remaining_pct }
                if ($w.period_end) {
                    $payload['period_end'] = [string]$w.period_end
                    $payload['reset'] = [string]$w.period_end
                }
            }
        } catch {}
        try {
            if (Get-Command Get-BobCursorAgentWeeklyRemaining -ErrorAction SilentlyContinue) {
                $c = Get-BobCursorAgentWeeklyRemaining
                $pcent = [ordered]@{}
                if ($null -ne $c.remaining_pct) { $pcent['cursor-models'] = [int]$c.remaining_pct }
                if ($null -ne $c.sand_remaining_pct) { $pcent['grok-weekly'] = [int]$c.sand_remaining_pct }
                if ($pcent.Count -gt 0) { $payload['pcent'] = [hashtable]$pcent }
                if ($c.period_end) { $payload['cursor_period_end'] = [string]$c.period_end }
            }
        } catch {}
        try {
            if (Get-Command Get-BobCapacity -ErrorAction SilentlyContinue) {
                $cap = Get-BobCapacity
                if ($cap -and $cap.cursor_models -and $null -ne $cap.cursor_models.remaining_pct) {
                    if (-not $payload.Contains('pcent')) { $payload['pcent'] = @{} }
                    $payload['pcent']['cursor-models'] = [int]$cap.cursor_models.remaining_pct
                }
            }
        } catch {}
    }
    return $payload
}

function Post-Report {
    param([hashtable]$Payload, [string]$Url)
    $secretPath = Join-Path $env:USERPROFILE '.grok\bob\report.secret'
    $secret = $env:BOB_REPORT_SECRET
    if (-not $secret -and (Test-Path $secretPath)) {
        $secret = (Get-Content $secretPath -Raw -Encoding UTF8).Trim()
    }
    if (-not $secret) {
        Write-Host 'INFO no report.secret; skip POST'
        return 0
    }
    $target = if ($Url) { $Url } elseif ($env:AGENTIC_IRC_REPORT_URL) { $env:AGENTIC_IRC_REPORT_URL } elseif ($env:BOB_REPORT_URL) { $env:BOB_REPORT_URL } else { 'http://irc.ntsa.uk:80/bob/v1/report' }
    $json = ($Payload | ConvertTo-Json -Compress -Depth 6)
    try {
        $resp = Invoke-WebRequest -Uri $target -Method POST -Body $json -ContentType 'application/json' -Headers @{ 'X-Bob-Secret' = $secret } -UseBasicParsing -TimeoutSec 20
        return [int]$resp.StatusCode
    } catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        Write-Host ("WARN post failed: {0}" -f $_)
        return 0
    }
}

$mid = Resolve-MachineId -Hint $Machine
Write-Host ("INFO Watch-BobDigestMetrics machine={0} interval={1}s" -f $mid, $IntervalSeconds)

while ($true) {
    $payload = Get-MetricsPayload -MachineId $mid
    if ($DryRun) {
        $payload | ConvertTo-Json -Depth 6
    } else {
        $code = Post-Report -Payload $payload -Url $ReportUrl
        Write-Host ("INFO metrics POST status={0} weekly={1}" -f $code, $payload['weekly'])
    }
    if ($Once) { break }
    Start-Sleep -Seconds ([Math]::Max(30, $IntervalSeconds))
}
