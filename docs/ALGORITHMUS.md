# Wie KANO den Energiebedarf berechnet

Dieses Dokument beschreibt nachvollziehbar, wie aus Profil, Gewicht und Tracking das tägliche
Kalorienziel entsteht. Code: `core/nutrition.py`, `core/trend.py`, `core/adaptive.py`,
`core/budget.py`, `services/energy.py`. Tests: `tests/test_nutrition.py`, `tests/test_trend_adaptive.py`.

## 1. Startwert (Formel)

**Grundumsatz (BMR)** nach Mifflin-St-Jeor (1990):

| | Formel |
|---|---|
| Männer | 10 · kg + 6,25 · cm − 5 · Jahre + 5 |
| Frauen | 10 · kg + 6,25 · cm − 5 · Jahre − 161 |
| divers/keine Angabe | Mittelwert der Konstanten (−78) |

**Gesamtumsatz (TDEE)** = BMR × Aktivitätsfaktor (1,2 / 1,375 / 1,55 / 1,725 / 1,9).

Als Gewicht dient – sobald vorhanden – das **Trendgewicht** (siehe 2), nicht der letzte Tageswert.

## 2. Gewichtstrend

Tageswerte schwanken um ±1–2 kg (Wasser, Salz, Verdauung). KANO glättet mit einem
zeitgewichteten exponentiellen Durchschnitt:

```
trend_neu = trend_alt + a · (gewicht − trend_alt)
a         = 1 − (1 − α)^Δt        α = 0,1,  Δt = Tage seit letzter Messung
```

Der Exponent Δt sorgt dafür, dass unregelmäßiges Wiegen den Trend nicht verzerrt.
Das **Tempo** (kg/Woche) ist die Steigung einer linearen Regression über die Trendwerte der
letzten 21 Tage (mind. 4 Messungen über ≥ 7 Tage).

## 3. Adaptiver Energiebedarf

Einmal pro Woche (beim ersten Öffnen ab Montag) wird neu gerechnet. Grundlage ist die
Energiebilanz über die letzten **28 Tage**:

```
TDEE_beobachtet = Ø Energiezufuhr − (Δ Trendgewicht [kg] · 7.700 kcal/kg) / Tage
```

**Datenqualität – nur dann wird adaptiv gerechnet:**

* ≥ 10 vollständig getrackte Tage im Fenster. Tage mit < 50 % des Ziels (mind. 700 kcal)
  gelten als *unvollständig getrackt* und werden ignoriert – sonst würde „vergessenes“ Tracken
  den Verbrauch künstlich senken.
* ≥ 4 Wägungen, die ≥ 14 Tage auseinanderliegen.

**Vorsichtige Übernahme:**

```
Vertrauen  c = (getrackte Tage / 28) · min(1, Spannweite / 21)       ∈ [0, 1]
Anteil     k = 0,3 + 0,4 · c                                       ∈ [0,3; 0,7]
Vorschlag    = Basis + k · (TDEE_beobachtet − Basis)
Schritt      = begrenzt auf ±150 kcal pro Woche (±250 beim ersten Wechsel von der Formel)
Ergebnis     = begrenzt auf [1,1 · BMR ; 2,4 · BMR]
```

*Basis* ist die letzte adaptive Schätzung bzw. – solange es keine gibt – die Formel.

**Warum so?** Einzelne Wochen sind verrauscht (Feiertage, Wassereinlagerungen, Messfehler beim
Tracken). Die Dämpfung verhindert Sprünge, die sich wie „Bestrafung“ anfühlen würden, und
konvergiert trotzdem innerhalb weniger Wochen zum tatsächlichen Verbrauch.

## 4. Vom Bedarf zum Ziel – mit harten Sicherheitsgrenzen

| Ziel | Anpassung |
|---|---|
| Abnehmen | Defizit = Tempo · 7.700 / 7, **höchstens** 1 % Körpergewicht/Woche **und** 25 % des TDEE |
| Halten | kein Defizit |
| Muskelaufbau | +250 kcal |

* Das Tagesziel fällt **nie** unter 1.200 kcal (Frauen), 1.500 kcal (Männer), 1.350 kcal (divers).
* Kein Defizit bei BMI < 18,5, unter 18 Jahren oder wenn im Onboarding Schwangerschaft/Stillzeit,
  Essstörung oder ärztlich begleitete Ernährung angegeben wurde.
* Sinkt der Trend über 3 Wochen schneller als 1 % des Körpergewichts pro Woche, zeigt KANO einen
  freundlichen Hinweis (kein Alarm, keine rote Farbe).

## 5. Makronährstoffe

* Protein 1,6 g/kg (High Protein 2,0 g/kg), bezogen auf das Mittel aus aktuellem und Zielgewicht,
  höchstens 35 % der Energie.
* Fett 30 % (Low Carb 40 %), mindestens 0,6 g/kg.
* Kohlenhydrate: Rest (Low Carb höchstens 25 %).

## 6. Flexibles Wochenbudget

Wochenbudget = 7 × Tagesziel. Geplante Ausnahmetage (z. B. Geburtstag mit 2.600 kcal) werden
eingetragen; die Differenz wird gleichmäßig auf die **verbleibenden normalen Tage ab heute** verteilt.

* Kein Tag unter den Mindestwert, kein Tag mehr als 30 % unter dem normalen Ziel.
* Was nicht verteilbar ist, bleibt offen – mit dem Hinweis, dass eine Woche nicht perfekt aufgehen muss.
* Vergangene Tage werden nie verändert, und tatsächliches Mehr-Essen wird **bewusst nicht**
  ausgeglichen. Nur *geplante* Ausnahmen zählen – das verhindert Kompensations- und Schuldspiralen.
