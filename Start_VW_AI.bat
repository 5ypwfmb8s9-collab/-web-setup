@echo off
setlocal
cd /d "%~dp0"
set LOG=%~dp0start_log.txt

echo ============================================
echo   DISPO PRO wird gestartet
echo ============================================
echo.
echo Ein Log dieses Starts wird gespeichert in:
echo %LOG%
echo.

echo [1/4] Suche nach Updates...
where git >nul 2>&1
if errorlevel 1 (
    echo Git ist nicht installiert - Update wird uebersprungen, es startet der
    echo aktuell vorhandene Stand. Fuer automatische Updates bitte Git
    echo installieren ^(https://git-scm.com/download/win^).
    echo.
) else (
    if exist "%~dp0.git" (
        git pull 1>>"%LOG%" 2>&1
        if errorlevel 1 (
            echo Update fehlgeschlagen ^(z. B. kein Internet oder lokale
            echo Aenderungen^) - es startet der aktuell vorhandene Stand.
            echo Details stehen in: %LOG%
            echo.
        ) else (
            echo OK.
            echo.
        )
    ) else (
        echo Kein Git-Ordner gefunden - Update wird uebersprungen, es startet
        echo der aktuell vorhandene Stand.
        echo.
    )
)

echo [2/4] Pruefe Python...
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

echo [3/4] Installiere/aktualisiere benoetigte Pakete...
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

echo [4/4] Starte das Programm - der Browser oeffnet sich gleich automatisch.
echo Zum Beenden einfach dieses Fenster schliessen.
echo ============================================
echo.
python -m streamlit run app.py

echo.
echo Das Programm wurde beendet.
pause
