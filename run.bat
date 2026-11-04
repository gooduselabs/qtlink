@echo off
REM QTLink - chay that tren Windows. Sua config.yaml truoc. Dat mat khau: set QTLINK_SFTP_PASS=...
cd /d %~dp0
call .venv\Scripts\activate.bat
python -m qtlink run -c config.yaml
