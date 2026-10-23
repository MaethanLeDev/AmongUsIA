@echo off
chcp 65001 >nul
title Classe Noire - L'espion
cd /d "%~dp0"
rem Broker MQTT : amongus.local, sinon 10.109.150.215 (Niels). Autre broker : set MQTT_HOST=<ip>   Autre port : set PORT=<port>
node server.js
pause
