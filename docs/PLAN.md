# KANO – Projektplan

Dieses Dokument beschreibt Aufbau, Datenmodell und die Phasen, in denen KANO gebaut wurde.
Alle Architekturentscheidungen, die über den ursprünglichen Auftrag hinausgehen, stehen
gesammelt unter **„Entscheidungen zur Freigabe“** – dort lässt sich jede davon mit
überschaubarem Aufwand ändern.

## 1. Projektstruktur

```
app.py                     Einstiegspunkt: Seitenkonfiguration, Login-Weiche, Navigation
.streamlit/config.toml     Dunkles Theme, Inter als Schrift, Toolbar minimal
.streamlit/secrets.toml.example   Vorlage für API-Key & Datenbank-URL (echte Datei nie committen)
assets/styles.css          Zentrales CSS (Design-System)
static/                    Icons für den Home-Bildschirm (per Static Serving ausgeliefert)
core/                      Reine Fachlogik ohne Streamlit – vollständig per pytest getestet
  clock.py                 „Heute“ in Europe/Berlin
  nutrition.py             Mifflin-St-Jeor, Aktivitätsfaktoren, Makros, Sicherheitsgrenzen
  trend.py                 Gewichtstrend (zeitgewichteter exponentieller Durchschnitt)
  adaptive.py              Adaptiver Energiebedarf (siehe docs/ALGORITHMUS.md)
  budget.py                Flexibles Wochenbudget
  safety.py                Warnzeichen, Hinweise, Hilfsangebote
  schedule.py              Schichtmodelle → Mahlzeitenzeiten
  portions.py              Ungefähr-Modus (klein/mittel/groß)
  basic_foods.py           Kleine Offline-Lebensmittelliste (Grundnahrungsmittel)
  pricing.py               Standard-Preistabelle + Schnittstelle für echte Angebotsdaten
  shopping.py              Einkaufsliste aus dem Plan (Bereiche, Skalierung)
  patterns.py              Favoriten-/Mustervorschläge („Wie letzten Dienstag?“)
  insights.py              Lokale Mustererkennung für den Coach
  features.py              Feature-Flags free/premium
db/                        Datenzugriffsschicht (SQLAlchemy Core)
  engine.py                Verbindung: SQLite lokal, PostgreSQL/Supabase per DATABASE_URL
  schema.py                Tabellendefinitionen
  repo.py                  Alle Lese-/Schreibfunktionen – Seiten sprechen nie direkt SQL
services/                  Anbindung nach außen
  auth.py                  Registrierung, Login (scrypt), „Angemeldet bleiben“-Token
  ai.py / ai_schemas.py    Claude: Freitext, Foto, Wochenplan, Reste, Coach, Wochenauswertung
  openfoodfacts.py         Produktsuche & Barcode inkl. Cache
  barcode.py               Barcode aus Foto lesen (zxing-cpp)
  coach_context.py         Datenzusammenfassung für den Coach (keine Rohdaten)
  exporter.py / importer.py  CSV/PDF-Export, CSV-Import
ui/                        Design-System & wiederverwendbare Komponenten
  theme.py                 CSS laden, Home-Bildschirm-Meta-Tags, Logo
  components.py            Fortschrittsring, Balken, Karten, Navigation unten
  charts.py                Altair-Diagramme im Gradient-Stil
  session.py               Angemeldeter Nutzer, Profil-Cache
  food_forms.py            Gemeinsame Eingabemasken fürs Tracking
pages/                     Die sechs Hauptseiten + Login + Onboarding
tests/                     pytest (Fachlogik, Datenbank, Services) + Streamlit-AppTests
```

## 2. Datenmodell

| Tabelle | Zweck | Wichtige Felder |
|---|---|---|
| `users` | Konten | email (unique), password_hash, tier (`free`/`premium`), failed_logins, locked_until |
| `auth_tokens` | „Angemeldet bleiben“ | token_hash, user_id, expires_at |
| `profiles` | Profil & Einstellungen (1:1) | sex, birth_year, height_cm, activity, goal, pace_kg_week, goal_weight_kg, diet_type, dislikes, hide_numbers, approx_mode, ai_consent, household_size, weekly_budget_eur, shift_pattern (JSON), onboarding_done, disclaimer_accepted_at |
| `foods` | Lebensmittel-Cache (Open Food Facts) & eigene Produkte | source, barcode, name, brand, kcal/Protein/KH/Fett/Ballaststoffe je 100 g, serving_g |
| `food_log` | Getrackte Einträge | date, meal, name, grams, size_label, kcal, protein, carbs, fat, source, group_id |
| `favorites` | Gemerkte Mahlzeiten | name, meal, items (JSON), use_count, last_used |
| `weights` | Gewicht (1 Wert pro Tag) | date, weight_kg, source |
| `activities` | Importierte Aktivität | date, kind, kcal, steps, minutes |
| `wellbeing` | Ziele über die Waage hinaus (1 pro Tag) | energy, sleep_hours, sleep_quality, mood, hunger, waist_cm, note |
| `strength` | Kraftwerte | date, exercise, weight_kg, reps |
| `energy_targets` | Wöchentliche Zielberechnung (Historie) | week_start, tdee, target_kcal, method, confidence, explanation |
| `day_exceptions` | Flexible Woche (Geburtstag etc.) | date, planned_kcal, note |
| `shift_days` | Schicht je Datum (überschreibt Wochenmuster) | date, shift |
| `meal_plans` | Generierte Wochenpläne | week_start, params (JSON), plan (JSON) |
| `shopping_items` | Einkaufsliste | plan_id, name, qty, unit, section, checked, custom |
| `prices` | Editierbare Preistabelle je Nutzer | item, unit, pack_qty, price_eur, section |
| `coach_messages` | Chatverlauf | role, content |
| `coach_reports` | Wöchentliche Kurzauswertung | week_start, content |

Alle nutzerbezogenen Tabellen hängen per Fremdschlüssel mit `ON DELETE CASCADE` an `users`,
sodass „Konto löschen“ wirklich alles entfernt.

## 3. Phasen

1. Projektstruktur, Design-System, Login, Onboarding mit Kalorienberechnung, Datenbank.
2. Tracking: Lebensmittelsuche, Barcode, Freitext mit Claude, Favoriten, Tagesübersicht mit Ring.
3. Gewicht, Trend, adaptiver Energiebedarf, flexibles Wochenbudget.
4. Foto-Tracking, Wochenplan, Einkaufsliste, Resteverwertung, Budget-Modus, Schichten, Meal Prep.
5. KI-Coach, Ziele über die Waage hinaus, Sicherheitsfunktionen, Import/Export, Feature-Flags.
6. Feinschliff: Mobile-Test, Ladezeiten, Fehlerbehandlung, README, Deployment.

Jede Phase ist ein eigener Commit; nach jedem Commit startet die App und alle Tests laufen durch.

## 4. Entscheidungen zur Freigabe

Diese Punkte waren im Auftrag nicht festgelegt. Ich habe jeweils eine vernünftige Standardlösung
gewählt; bitte kurz bestätigen oder ändern:

1. **SQLAlchemy Core als Datenzugriffsschicht.** Der Wechsel auf Supabase/PostgreSQL bedeutet nur,
   `DATABASE_URL` in den Secrets zu setzen (+ `psycopg` installieren). Kein ORM, keine Migrationstool-Abhängigkeit
   (Tabellen werden beim Start angelegt). Für spätere Schemaänderungen wäre Alembic der nächste Schritt.
2. **Passwort-Hashing mit `hashlib.scrypt`** (Standardbibliothek) statt bcrypt – keine 72-Byte-Grenze,
   keine zusätzliche Abhängigkeit.
3. **„Angemeldet bleiben“ per Cookie.** Streamlit verliert die Sitzung beim Neuladen – ohne das
   müsste man sich bei jedem Öffnen vom Home-Bildschirm neu anmelden. Das Cookie enthält nur ein
   zufälliges Token (in der DB gehasht gespeichert, 30 Tage gültig, beim Abmelden gelöscht).
4. **Claude-Modell** `claude-opus-5` als Standard, per `ANTHROPIC_MODEL` in den Secrets änderbar
   (z. B. auf ein günstigeres Modell). Server-seitige Fallbacks bei Ablehnungen sind aktiviert.
5. **Ausdrückliche KI-Einwilligung.** Gesundheitsdaten sind besonders geschützt (Art. 9 DSGVO).
   Bevor Daten an die Anthropic API gehen, muss der Nutzer zustimmen; ohne Zustimmung funktioniert
   alles außer den KI-Funktionen.
6. **Offline-Grundnahrungsmittel.** Zusätzlich zu Open Food Facts gibt es eine kleine eingebaute Liste
   (≈100 Grundnahrungsmittel mit Durchschnittswerten), damit Suche und Ungefähr-Modus auch ohne
   Netz bzw. bei OFF-Ausfall funktionieren.
7. **Flexible Woche verteilt nur geplante Ausnahmen**, nicht vergangene „Überschreitungen“ –
   bewusst, um kein Kompensations-/Schuldverhalten zu fördern.
8. **Barcode aus Foto mit `zxing-cpp`** (reine pip-Wheels, läuft auf Streamlit Cloud ohne Systempakete),
   bei Misserfolg liest Claude die Ziffern unter dem Barcode.
