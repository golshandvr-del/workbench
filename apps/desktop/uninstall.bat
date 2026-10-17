@echo off
setlocal
set "AIWB_APP_DIR=%LOCALAPPDATA%\Programs\AIWorkbench"
set "AIWB_APP_DATA=%LOCALAPPDATA%\AIWorkbench"
echo This removes AI Workbench program files and shortcuts.
echo Your settings and backup files in "%AIWB_APP_DATA%" will be kept.
choice /m "Continue with uninstall"
if errorlevel 2 exit /b 0
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $s=New-Object -ComObject WScript.Shell; $paths=@((Join-Path ([Environment]::GetFolderPath('Desktop')) 'AI Workbench.lnk'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AI Workbench.lnk')); foreach($p in $paths){Remove-Item -LiteralPath $p -Force}; Remove-Item -LiteralPath $env:AIWB_APP_DIR -Recurse -Force; Write-Host 'AI Workbench program removed. Settings and backups were kept.'"
echo.
pause
