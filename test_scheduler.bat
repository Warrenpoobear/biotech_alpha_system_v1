@echo off
echo === WAKE ROBIN TASK SCHEDULER TEST ===
echo Date: %date% %time%
echo Current Directory: %cd%
echo.

cd /d "C:\Users\DarrenSchulz\Brooks Capital Management\Investment - Documents\Research\Biotechnology\Alpha Model Files\biotech_alpha_system_v1"
echo Changed to: %cd%
echo.

echo Testing Python availability...
python --version
echo.

echo Running production pipeline...
python run_production.py --date 2026-01-02

echo.
echo === TEST COMPLETE ===
echo Error Level: %errorlevel%
pause
