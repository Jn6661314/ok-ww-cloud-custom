@echo off
setlocal
call "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat" >nul 2>&1
if errorlevel 1 (
    echo [error] vcvars64 failed - install Visual Studio 2022 C++ workload
    exit /b 1
)
cd /d "%~dp0"
cl /nologo /O2 /MT /Fe:ok-ww.exe launcher.c /link shlwapi.lib user32.lib
if errorlevel 1 ( echo [error] cl failed & exit /b 1 )
mt -nologo -manifest launcher.manifest -outputresource:ok-ww.exe;1
if errorlevel 1 ( echo [error] mt failed & exit /b 1 )
echo [ok] built: %~dp0ok-ww.exe
