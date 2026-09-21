@echo off
rem Build 32-bit ANSI airc-moot-thin.exe. Run from an x86 MSVC prompt
rem (GHA: ilammy/msvc-dev-cmd with arch=x86).
setlocal
cd /d "%~dp0"
rc /nologo /fo airc-moot-thin.res airc-moot-thin.rc
if errorlevel 1 exit /b 1
cl /nologo /O2 /W3 /DWIN32 /DWINVER=0x0501 /D_WIN32_WINNT=0x0501 /D_CRT_SECURE_NO_WARNINGS ^
  main.c util.c aes256gcm.c config.c jail.c moot.c dumb_job.c irc_tls.c pair.c beacon.c task_ui.c ^
  /Fe:airc-moot-thin.exe /link ws2_32.lib secur32.lib crypt32.lib advapi32.lib wininet.lib airc-moot-thin.res
if errorlevel 1 exit /b 1
echo built airc-moot-thin.exe
endlocal
