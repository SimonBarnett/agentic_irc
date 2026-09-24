# Digest chair (Jeeves): #bobiverse + every #{machine} shop (issue #100 / Simon 2026-09-22).
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here 'irc_agent.py'
$home = if ($env:AGENTIC_IRC_HOME) { $env:AGENTIC_IRC_HOME } else { Join-Path $env:USERPROFILE '.agentic-irc-bobiverse' }
$nick = if ($env:AGENTIC_IRC_CHAIR_NICK) { $env:AGENTIC_IRC_CHAIR_NICK } else { 'Jeeves' }
$env:AGENTIC_IRC_CHAIR_NICK = $nick
& python -c "import sys; sys.path.insert(0, r'$here'); import bobreport; bobreport.persist_chair_nick(r'$home', r'$nick')"
# --channel is ignored for channel list when --chair; chair_channels() wins.
& python $py --nick $nick --channel '#bobiverse' --home $home --chair @args
