@echo off
title Void ^& Draconic Server
set PACK=https://raw.githubusercontent.com/Bresqwik/void-draconic-pack/main/pack.toml
set BOOT=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar
if not exist run.bat (
  echo NeoForge ist noch nicht installiert. Bitte zuerst install.bat ausfuehren.
  pause
  exit /b 1
)
if not exist packwiz-installer-bootstrap.jar powershell -NoProfile -Command "Invoke-WebRequest -Uri '%BOOT%' -OutFile 'packwiz-installer-bootstrap.jar'"
java -jar packwiz-installer-bootstrap.jar -g -s server %PACK%
if errorlevel 1 echo Pack-Update fehlgeschlagen, starte mit den vorhandenen Mods.
call run.bat nogui
pause
