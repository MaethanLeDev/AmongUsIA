@echo off
chcp 65001 >nul
title Classe Noire
cd /d "%~dp0"
rem Pour relier les Raspberry Pi : set MQTT_HOST=<ip du broker>
node server.js
pause
