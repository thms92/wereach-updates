@echo off
REM Arret LinkedIn Scraper - Windows (double-clic)
cd /d "%~dp0"
echo Arret de LinkedIn Scraper...
docker compose down
echo.
echo Arrete.
pause
