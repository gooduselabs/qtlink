@echo off
REM QTLink - chay demo tren Windows (can Python 3.10+ tu python.org)
cd /d %~dp0
if not exist .venv ( py -3 -m venv .venv )
call .venv\Scripts\activate.bat
pip install -r requirements.txt
start http://localhost:8080
python -m qtlink demo
