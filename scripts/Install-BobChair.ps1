# Digest chair seat on ionos: #bobiverse only, !bobiverse + webhook digest (issue #73).
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here 'irc_agent.py'
$home = if ($env:AGENTIC_IRC_HOME) { $env:AGENTIC_IRC_HOME } else { Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
$nick = if ($env:AGENTIC_IRC_CHAIR_NICK) { $env:AGENTIC_IRC_CHAIR_NICK } else { 'bob-chair' }
$env:AGENTIC_IRC_CHAIR_NICK = $nick
& python $py --nick $nick --channel '#bobiverse' --home $home --chair @args
