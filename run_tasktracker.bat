@echo off
cd /d "%~dp0"
rem pyw = no Python console; start = batch exits so no cmd window stays open
start "" pyw -3.11 -m tasktracker
