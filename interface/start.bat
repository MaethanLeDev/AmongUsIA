@echo off
chcp 65001 >nul
title Classe Noire
cd /d "%~dp0"
rem Broker MQTT : 10.109.150.215 par defaut (Niels). Autre broker : set MQTT_HOST=<ip>  /  sans MQTT : set MQTT_HOST=off
node server.js
pause
