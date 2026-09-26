# FR #238: sanctioned detached irc_agent + irc_listen pair (Windows).
# Seat agents must NEVER start IRC from a tool shell — report on outbox and let
# Watch-AgentHealth "irc ensure" run. Ops/recovery: use this script so the
# coordinator is the seat monitor PID (not the short-lived launcher).
#
# Example (watch seat):
#   .\Start-IrcPair.ps1 -IrcHome $env:USERPROFILE\.agentic-irc-watch-grok `
#     -Nick marchhare-31712 -CoordinatorPid 31712 -Channel '#marchhare'
#
# Do not use $Home (read-only). UTF-8 no BOM.
param(
    [Parameter(Mandatory = $true)][string]$IrcHome,
    [Parameter(Mandatory = $true)][string]$Nick,
    [Parameter(Mandatory = $true)][int]$CoordinatorPid,
    [string]$Channel = '',
    [string]$Scripts = $PSScriptRoot,
    [string]$HostName = $(if ($env:AGENTIC_IRC_HOST) { $env:AGENTIC_IRC_HOST } else { 'irc.ntsa.uk' }),
    [string]$Port = $(if ($env:AGENTIC_IRC_PORT) { $env:AGENTIC_IRC_PORT } else { '6697' }),
    [switch]$NoBreakaway,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$py = (Get-Command python -ErrorAction Stop).Source
$launcher = Join-Path $Scripts 'start_irc_pair.py'
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "missing start_irc_pair.py under $Scripts"
}
$resolved = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($IrcHome))
$argList = @(
    '-u', $launcher,
    '--coordinator-pid', "$CoordinatorPid",
    '--home', $resolved,
    '--nick', $Nick,
    '--host', $HostName,
    '--port', "$Port",
    '--python', $py
)
if ($Channel) { $argList += @('--channel', $Channel) }
if ($NoBreakaway) { $argList += '--no-breakaway' }
if ($DryRun) { $argList += '--dry-run' }
& $py @argList
if ($LASTEXITCODE -ne 0) {
    throw "start_irc_pair.py failed exit=$LASTEXITCODE"
}
