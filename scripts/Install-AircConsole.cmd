@echo off
REM FR #256: unsigned downloadable install must not depend on machine ExecutionPolicy.
REM Run elevated. Unblocks Mark-of-the-Web then launches with Bypass.
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%HERE%' -Filter *.ps1 | Unblock-File -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Install-AircConsole.ps1" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo ERROR Install-AircConsole failed exit %EC%
  exit /b %EC%
)
echo INFO Install-AircConsole.cmd done
exit /b 0
