@echo off
setlocal
cd /d "%~dp0"
set LOG=%~dp0start_log.txt

echo ============================================
echo   VW AI wird gestartet
echo ============================================
echo.
echo Ein Log dieses Starts wird gespeichert in:
echo %LOG%
echo.

echo [1/3] Pruefe Python...
python --version 1>>"%LOG%" 2>&1
if errorlevel 1 (
    echo.
    echo FEHLER: Python wurde nicht gefunden.
    echo Bitte zuerst Python installieren ^(z.B. ueber den Microsoft Store^)
    echo und dieses Fenster danach neu starten.
    echo.
    pause
    exit /b 1
)
python --version
echo OK.
echo.

if not exist "%~dp0requirements.txt" (
    echo FEHLER: Datei "requirements.txt" fehlt in diesem Ordner.
    echo Bitte den kompletten Programmordner verwenden, nicht nur diese BAT-Datei.
    echo.
    pause
    exit /b 1
)

echo [2/3] Installiere/aktualisiere benoetigte Pakete...
echo ^(Beim allerersten Start kann das ein paar Minuten dauern.^)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Continue'; & python -m pip install -r requirements.txt 2>&1 | Tee-Object -FilePath '%LOG%' -Append; exit $LASTEXITCODE"
if errorlevel 1 (
    echo.
    echo FEHLER beim Installieren der Pakete.
    echo Details stehen in: %LOG%
    echo.
    pause
    exit /b 1
)
echo.
echo OK.
echo.

echo [3/3] Starte das Programm - der Browser oeffnet sich gleich automatisch.
echo Zum Beenden einfach dieses Fenster schliessen.
echo ============================================
echo.
python -m streamlit run app.py

echo.
echo Das Programm wurde beendet.
pause
