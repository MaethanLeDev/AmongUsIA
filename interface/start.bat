@echo off
chcp 65001 >nul
title Classe Noire - L'espion
cd /d "%~dp0"
rem Broker MQTT : localhost, sinon amongus.local, sinon 10.109.150.215 (Niels). Autre broker : node server.js --broker <ip>
node server.js %*
pause
