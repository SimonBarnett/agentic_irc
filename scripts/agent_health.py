"""Watch-AgentHealth helpers (issue #135 / #144): IRC TSR probe + session store."""
from __future__ import annotations
from agent_health_core import *  # noqa: F401,F403
from agent_health_cli import _cli
if __name__ == "__main__":
    raise SystemExit(_cli())
