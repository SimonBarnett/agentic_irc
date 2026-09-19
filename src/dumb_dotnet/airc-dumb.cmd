@echo off
REM Scheduled-task wrapper. Fill nick/channel/home/operators/allow-path on the 2012 box.
REM Protocol clone of scripts/dumb_agent.py. Empty --operators is refused.
"%~dp0airc-dumb.exe" %*
