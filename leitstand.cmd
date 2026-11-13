@echo off
rem Startet den Leitstand (Stufe 5) und oeffnet den Browser. Dieses Fenster schliessen beendet den Server.
title Leitstand (Lab 2) - Fenster schliessen beendet den Server
cd /d "%~dp0"
".venv\Scripts\python.exe" -m entwicklung leitstand
if errorlevel 1 pause
