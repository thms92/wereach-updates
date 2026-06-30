@echo off
REM Lanceur LinkedIn Scraper - Windows (double-clic)
cd /d "%~dp0"
cls
echo ============================================
echo    LinkedIn Scraper - Demarrage
echo ============================================
echo.

echo Verification de Docker...
docker info >nul 2>&1
if errorlevel 1 (
  echo.
  echo Docker ne tourne pas.
  echo  - Ouvre l'application "Docker Desktop", attends qu'elle demarre,
  echo    puis double-clique a nouveau sur ce fichier.
  echo.
  pause
  exit /b 1
)
echo Docker OK
echo.

echo Demarrage de l'application...
echo (La toute premiere fois peut prendre quelques minutes, c'est normal.)
docker compose up -d --build

echo.
echo Attente du demarrage...
timeout /t 15 /nobreak >nul

echo Ouverture du navigateur...
start http://localhost:8501
echo.
echo ============================================
echo  L'app est ouverte sur http://localhost:8501
echo  Pour l'arreter : double-clique sur stop.bat
echo ============================================
echo.
pause
