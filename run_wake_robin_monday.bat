@echo off
echo =================================================================
echo WAKE ROBIN PRODUCTION RUN - MONDAY SCHEDULE
echo Date: %date% %time%
echo =================================================================
echo.

cd /d "C:\Users\DarrenSchulz\Brooks Capital Management\Investment - Documents\Research\Biotechnology\Alpha Model Files\biotech_alpha_system_v1"

echo Calculating previous Friday's date...
rem Simple logic: If today is Monday, Friday is 3 days ago
rem For testing on Friday, use today

rem Get today's day of week (0=Sunday, 1=Monday, ..., 6=Saturday)
for /f %%a in ('powershell -Command "(Get-Date).DayOfWeek.value__"') do set DOW=%%a

echo Today is day of week: %DOW%

rem If today is Monday (2), use Friday (5) which is 3 days ago
rem For now, we'll just use 2026-01-02 for testing
set RUN_DATE=2026-01-02

echo.
echo Running pipeline for date: %RUN_DATE%
python run_production.py --date %RUN_DATE%

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
