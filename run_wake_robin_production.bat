@echo off
echo =================================================================
echo WAKE ROBIN PRODUCTION RUN
echo Date: %date% %time%
echo =================================================================
echo.

cd /d "C:\Users\DarrenSchulz\Brooks Capital Management\Investment - Documents\Research\Biotechnology\Alpha Model Files\biotech_alpha_system_v1"

echo Running production pipeline for previous Friday...
python run_production.py

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Production pipeline completed successfully
) else (
    echo.
    echo [FAILED] Production pipeline failed with error level %errorlevel%
    echo Check logs/errors/ directory for details
)

echo.
echo =================================================================
echo COMPLETE
echo =================================================================
