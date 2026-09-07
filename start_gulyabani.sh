#!/usr/bin/env bash
# ---------------------------------------------------------------
#  GÜLYABANI — Start als Streamlit-App
#  Baut bei Bedarf das Spiel und öffnet dann den Browser.
# ---------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f dist/embed.html ]; then
  echo "Spiel-Build fehlt, wird erzeugt..."
  if ! command -v node >/dev/null 2>&1; then
    echo "FEHLER: Node.js wurde nicht gefunden. Bitte installieren und 'node build.js' ausführen." >&2
    exit 1
  fi
  node build.js
fi

if ! command -v streamlit >/dev/null 2>&1; then
  echo "Streamlit wird installiert..."
  python3 -m pip install -r requirements.txt
fi

echo "Starte GÜLYABANI..."
exec streamlit run gulyabani_app.py
