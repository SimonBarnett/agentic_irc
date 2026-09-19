@echo off
setlocal
cd /d "%~dp0"
set "MSB="
if exist "%WINDIR%\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe" set "MSB=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe"
if exist "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe" if not defined MSB set "MSB=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe"
if not defined MSB (
  for /f "usebackq tokens=*" %%i in (`where msbuild 2^>nul`) do (
    set "MSB=%%i"
    goto :have
  )
)
:have
if not defined MSB (
  echo INFO no MSBuild
  exit /b 1
)
"%MSB%" "%~dp0airc-dumb.csproj" /p:Configuration=Release /p:TargetFrameworkVersion=v4.5 /v:m
if errorlevel 1 exit /b 1
if not exist "%~dp0airc-dumb.exe" (
  echo INFO build produced no airc-dumb.exe
  exit /b 1
)
echo INFO built %~dp0airc-dumb.exe
exit /b 0
