# KANO

**Ernährung tracken ohne Aufwand – und ohne Schuldgefühle.**
KANO ist eine mobile-first Ernährungs- und Abnehm-App mit Python + Streamlit: Freitext-, Foto- und
Barcode-Tracking, adaptiver Energiebedarf, alltagstaugliche Wochenpläne mit Einkaufsliste und ein
KI-Coach auf Basis von Claude. Komplett dunkel, minimalistisch, mit einem sparsam eingesetzten
Spectrum-Gradient.

<p>
<img src="docs/screenshots/heute.png" width="200" alt="Heute">
<img src="docs/screenshots/fortschritt.png" width="200" alt="Fortschritt">
<img src="docs/screenshots/plan.png" width="200" alt="Plan">
<img src="docs/screenshots/coach.png" width="200" alt="Coach">
</p>

## Funktionen

| Bereich | Was KANO kann |
|---|---|
| **Tracking** | Freitext („2 Scheiben Vollkornbrot mit Käse und ein Kaffee mit Milch“) → Claude zerlegt und schätzt · Foto → Claude Vision · Barcode per Foto oder Nummer → Open Food Facts · Suche (eingebaute Grundnahrungsmittel + Open Food Facts) · Favoriten, „Zuletzt gegessen“ und Vorschläge wie „Wie letzten Dienstag?“ · Korrektur mit einem Tipp (±Menge bzw. klein/mittel/groß) · Ungefähr-Modus |
| **Pläne** | Wochenplan nach Ziel, Tagesbudget, Ernährungsform und Abneigungen · Budget-Modus mit editierbarer Discounter-Preistabelle · Resteverwertung passend zum restlichen Tagesbudget · Einkaufsliste nach Supermarkt-Bereichen, abhakbar, für mehrere Personen · Schichtarbeit (Früh/Spät/Nacht/frei) mit angepassten Essenszeiten · Meal Prep |
| **Energiebedarf** | Startwert nach Mifflin-St-Jeor · adaptiver Verbrauch aus Gewichtstrend und Tracking (wöchentlich, gedämpft) · geglätteter Gewichtstrend · flexibles Wochenbudget mit Ausnahmetagen – siehe [docs/ALGORITHMUS.md](docs/ALGORITHMUS.md) |
| **Coach** | Lokale Mustererkennung (z. B. kleines Mittagessen → großer Abend) · wöchentliche Kurzauswertung · Chat mit Claude auf Basis einer datensparsamen Zusammenfassung |
| **Mehr als die Waage** | Energie, Schlaf, Hunger, Wohlbefinden, Taillenumfang, Kraftwerte – per Schieberegler |
| **Sicherheit** | Harte Untergrenzen (1.200/1.500 kcal), max. 1 % Körpergewicht/Woche, Hinweis bei zu schnellem Verlust oder sehr niedriger Zufuhr, Warnzeichen-Erkennung mit Hilfsangeboten, „Zahlen ausblenden“, kein Defizit bei Schwangerschaft/Essstörung/Untergewicht/Minderjährigen, keine roten Warnungen, keine Streaks |
| **Daten** | CSV-Import (Garmin, Google Fit, Waagen …) und Apple-Health-`export.xml` · Export als CSV-ZIP, Tagebuch-CSV und PDF-Bericht für Beratung/Arztpraxis · Konto vollständig löschen |
| **Freemium-vorbereitet** | Feature-Flags `free`/`premium` je Nutzer, aktuell alles freigeschaltet; Grundfunktionen bleiben dauerhaft kostenlos |

## Schnellstart (lokal)

Voraussetzung: Python 3.11 oder neuer.

```bash
git clone <dieses-repo> kano && cd kano
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# → ANTHROPIC_API_KEY eintragen (für Freitext, Foto, Plan, Coach)

streamlit run app.py
```

Die App läuft dann unter <http://localhost:8501>. Die Datenbank (`data/kano.db`) wird beim ersten
Start automatisch angelegt.

**Demo-Konto mit 5 Wochen Beispieldaten** (Gewicht, Tracking, Plan, Wohlbefinden):

```bash
python scripts/seed_demo.py            # → demo@kano.app / demo1234
```

**Ohne API-Schlüssel** funktionieren Suche, Barcode, Favoriten, Gewicht, Bedarf, Wochenbudget,
Muster, Import/Export – nur die KI-Funktionen sind dann ausgeblendet bzw. deaktiviert.

### Claude (Anthropic API)

1. API-Schlüssel unter <https://console.anthropic.com> erstellen.
2. In `.streamlit/secrets.toml` (lokal) bzw. in den App-Secrets (Cloud) eintragen:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   # optional, Standard ist claude-opus-5:
   # ANTHROPIC_MODEL = "claude-sonnet-5"
   ```
Der Schlüssel steht nie im Code. Nutzer müssen der KI-Nutzung im Onboarding bzw. im Profil
zustimmen (Gesundheitsdaten, Art. 9 DSGVO).

## Deployment auf Streamlit Community Cloud

1. Repository auf GitHub pushen.
2. Auf <https://share.streamlit.io> → **Create app** → Repository, Branch und `app.py` wählen.
3. Unter **Advanced settings** Python 3.11+ wählen und die Secrets einfügen (Inhalt wie
   `.streamlit/secrets.toml.example`).
4. **Deploy.**

> ⚠️ **Wichtig:** Streamlit Community Cloud speichert Dateien nicht dauerhaft. Die lokale SQLite-Datei
> geht bei jedem Neustart verloren. Für echte Nutzung eine externe Datenbank verwenden (nächster Abschnitt).

### Dauerhafte Datenbank mit Supabase (PostgreSQL)

1. Kostenloses Projekt auf <https://supabase.com> anlegen.
2. **Project Settings → Database → Connection string** kopieren (für Streamlit Cloud den
   *Session pooler* nehmen, er funktioniert über IPv4).
3. In den Secrets eintragen – wichtig ist das Präfix `postgresql+psycopg://`:
   ```toml
   DATABASE_URL = "postgresql+psycopg://postgres.xxxx:PASSWORT@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
   ```
4. App neu starten – die Tabellen werden automatisch angelegt.

Die gesamte Datenzugriffsschicht (`db/`) nutzt SQLAlchemy Core und ist gegen SQLite **und**
PostgreSQL 16 getestet (siehe Tests).

## Zum Home-Bildschirm hinzufügen

KANO verhält sich dann wie eine App (eigenes Icon, Vollbild, dunkle Statusleiste):

- **iPhone (Safari):** Seite öffnen → **Teilen** (Quadrat mit Pfeil) → **„Zum Home-Bildschirm“** → Hinzufügen.
- **Android (Chrome):** Seite öffnen → **Menü ⋮** → **„Zum Startbildschirm hinzufügen“** bzw. „App installieren“.

Mit „Angemeldet bleiben“ (Standard) bleibt man 30 Tage eingeloggt.
Tipp: Spracheingabe funktioniert überall über das Mikrofon der Handytastatur.

## Projektstruktur

```
app.py              Einstieg: Seitenkonfiguration, Login-Weiche, Navigation, Fehlergrenze
pages/              Heute · Tracken · Plan · Fortschritt · Coach · Profil · Login · Onboarding
core/               Reine Fachlogik (ohne Streamlit): Formeln, Trend, adaptiver Bedarf,
                    Wochenbudget, Sicherheit, Schichten, Portionen, Preise, Einkaufsliste, Muster
db/                 Datenzugriff (SQLAlchemy Core): engine.py, schema.py, repo.py
services/           Claude, Open Food Facts, Barcode, Auth, Planung, Coach-Kontext, Import/Export
ui/                 Design-System: Theme/CSS-Injektion, Komponenten, Diagramme, Formulare
assets/styles.css   Zentrales CSS
static/             App-Icons (Gradient-„K“)
scripts/            seed_demo.py · mobile_check.py · make_icons.py
tests/              pytest-Suite (Fachlogik, DB, Services, gemockte Claude-Aufrufe, AppTests)
docs/               PLAN.md (Plan & offene Entscheidungen) · ALGORITHMUS.md
```

Mehr zu Aufbau, Datenmodell und Entscheidungen: [docs/PLAN.md](docs/PLAN.md).

## Tests

```bash
pip install pytest
pytest                                  # gegen SQLite (schnell, ~15 s)

# optional gegen PostgreSQL:
KANO_TEST_DATABASE_URL="postgresql+psycopg://postgres@localhost:5432/kano_test" pytest
```

Die Suite deckt Formeln und Sicherheitsgrenzen, Trend und adaptiven Bedarf, Wochenbudget,
Auth und Konto-Löschung, Open Food Facts (gemockt), Barcode-Erkennung, alle Claude-Aufrufe
(gemockter HTTP-Transport inkl. Streaming – geprüft werden Modell, Effort, Structured Output
und Fallback-Header), Import/Export sowie einen Rauchtest, der jede Seite mit Demodaten
rendert und einen Datenbankausfall simuliert.

**Mobiler Klick-Test** mit Screenshots (App muss laufen, `pip install playwright && playwright install chromium`):

```bash
python scripts/mobile_check.py http://localhost:8501 screenshots 390
```

## Datenschutz & Verantwortung

- Passwörter nur als scrypt-Hash; „Angemeldet bleiben“ speichert nur den Hash eines Zufallstokens.
- KI nur mit Einwilligung; an Claude gehen nur die jeweils nötigen Angaben (Text/Foto zur Erkennung,
  eine verdichtete Zusammenfassung für Coach und Pläne – nie E-Mail, Passwort oder Name). Fotos
  werden nicht gespeichert.
- Export aller Daten und vollständiges Löschen des Kontos jederzeit im Profil.
- KANO ist **kein Medizinprodukt** und ersetzt keine ärztliche oder ernährungstherapeutische Beratung.
  Bei Warnzeichen für problematisches Essverhalten verweist die App freundlich auf professionelle Hilfe
  (u. a. Infotelefon Essstörungen des BIÖG, ehem. BZgA: 0221 892031; TelefonSeelsorge 0800 111 0 111).

## Bekannte Grenzen

- Einige Standardtexte von Streamlit-Widgets (z. B. „Upload“/„15MB per file“ im Datei-Upload) sind
  englisch und lassen sich nicht übersetzen.
- `st.camera_input` nutzt auf manchen Handys die Frontkamera – für Barcodes ist „Foto“ (öffnet die
  normale Kamera-App) meist besser.
- Datenbankschema-Änderungen werden derzeit nicht migriert (Tabellen werden nur neu angelegt); vor
  größeren Schemaänderungen im Produktivbetrieb Alembic ergänzen.
- Die Nährwerte der eingebauten Grundnahrungsmittel sind Durchschnittswerte; KI-Schätzungen sind Schätzungen.
