@echo off
REM Scheduled-task wrapper. Fill nick/channel/home/operators/allow-path on the 2012 box.
REM This tree is a net45 stub until Phase 5 protocol clone lands; Python scripts/dumb_agent.py is the reference.
"%~dp0airc-dumb.exe" %*
