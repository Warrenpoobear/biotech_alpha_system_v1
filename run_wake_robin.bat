@echo off
echo Wake Robin Production Run - %date% %time%
cd /d "C:\Users\DarrenSchulz\Brooks Capital Management\Investment - Documents\Research\Biotechnology\Alpha Model Files\biotech_alpha_system_v1"
python run_production.py
if %errorlevel% equ 0 (
    echo [SUCCESS] Pipeline completed successfully
) else (
    echo [FAILED] Pipeline failed with error level %errorlevel%
)
pause
