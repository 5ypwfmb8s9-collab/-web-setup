@echo off
REM ---------------------------------------------------------------
REM  GULYABANI - Start als Streamlit-App
REM  Baut bei Bedarf das Spiel und oeffnet dann den Browser.
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist "dist\embed.html" (
  echo Spiel-Build fehlt, wird erzeugt...
  where node >nul 2>nul
  if errorlevel 1 (
    echo.
    echo FEHLER: Node.js wurde nicht gefunden.
    echo Node.js installieren, dann "node build.js" ausfuehren.
    echo.
    pause
    exit /b 1
  )
  node build.js || (echo Build fehlgeschlagen. & pause & exit /b 1)
)

where streamlit >nul 2>nul
if errorlevel 1 (
  echo Streamlit wird installiert...
  python -m pip install -r requirements.txt || (echo Installation fehlgeschlagen. & pause & exit /b 1)
)

echo Starte GULYABANI...
streamlit run gulyabani_app.py
pause
