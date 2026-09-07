# GÜLYABANI

Ein Survival-Horror-Ego-Shooter im Browser. Acht Kugeln. Eine Tür. Etwas geht hinter dir.

> In den Bergen Anatoliens erzählt man sich von einer Gestalt, die zwischen Mitternacht
> und dem ersten Gebet über verlassene Wege geht. Groß wie zwei Männer, in Fell und
> Ketten, mit einem Stock, der auf den Stein schlägt. *Gülyabani.*

---

## Spielen

**Als Streamlit-App:**

```
streamlit run gulyabani_app.py
```

Unter Windows genügt ein Doppelklick auf `Start_GULYABANI.bat`, unter macOS und
Linux `./start_gulyabani.sh`. Beide bauen das Spiel bei Bedarf und installieren
Streamlit, falls es fehlt.

**Ohne Streamlit:** `dist/gulyabani.html` im Browser öffnen. Eine einzige Datei,
keine Installation, kein Server, funktioniert auch komplett offline.

**Aus dem Quellcode:** einen beliebigen Webserver im Projektordner starten und
`index.html` aufrufen.

```
python3 -m http.server 8000
# dann http://localhost:8000 öffnen
```

Kopfhörer werden empfohlen. Der Geist ist über die Richtung seines Knurrens
auffindbar, lange bevor er sichtbar wird.

### Mausteuerung in Streamlit

Streamlit rendert Komponenten in einem iframe, dessen `sandbox`-Attribut
`allow-pointer-lock` **nicht** enthält:

```
sandbox="allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox
         allow-same-origin allow-scripts allow-downloads"
```

`requestPointerLock()` schlägt darin lautlos fehl, die Maus wird also nicht
eingefangen. Das Spiel erkennt das und schaltet automatisch auf Ersatzsteuerung
um: **ziehen zum Umsehen, klicken zum Schießen**. Ein Hinweis erscheint dann am
unteren Bildrand.

Für echte Mausteuerung gibt es oben in der Mitte den Knopf **Eigener Tab**. Er
öffnet dasselbe Spiel in einem eigenen Fenster. Weil `allow-popups-to-escape-
sandbox` gesetzt ist, verlässt dieses Fenster die Sandbox und darf die Maus
wieder einfangen.

---

## Regeln

| | |
|---|---|
| **Acht Patronen** | Mehr gibt es nicht. Kein Nachladen, kein Fund im Haus. |
| **Nur der Kopf zählt** | Körpertreffer gehen durch ihn hindurch wie durch Rauch. |
| **Jeder Kopfschuss** | reißt ihn zurück, verlangsamt ihn dauerhaft und schenkt Vorsprung. |
| **Drei Muskalar** | brechen das Siegel der Ausgangstür. |

Der Geist weiß immer ungefähr, wo du bist. Verstecken funktioniert nicht. Die
einzigen Währungen sind Abstand und Zeit.

### Steuerung

| Taste | Wirkung |
|---|---|
| `W` `A` `S` `D` | Bewegen |
| Maus | Umsehen |
| Maus ziehen | Umsehen, falls der Browser die Maus nicht einfängt |
| `Umschalt` | Sprinten, verbraucht Nefes (Atem) |
| `Strg` / `C` | Ducken, leiser und langsamer |
| Linke Maustaste | Schießen |
| Rechte Maustaste | Kimme und Korn — der einzige zuverlässige Kopfschuss |
| `F` | Taschenlampe |
| `G` | Stein werfen, lenkt den Geist ab |
| `E` | Benutzen, Tür, Aufheben |
| `Q` | Muska spüren, kostet Akıl (Verstand) |
| `Leertaste` | Losreißen, wenn er dich packt |
| `Esc` / `P` | Pause |

Auf Touchgeräten erscheinen ein Bewegungsstick links und Aktionstasten rechts.
Das Spiel ist für Querformat gebaut und weist im Hochformat darauf hin.

---

## Was drin steckt

**Der Geist.** Wegfindung über eine Breitensuche im Zellenraster, mit den Zuständen
Jagen, Nachgehen, Taumeln, Tür aufbrechen und Zupacken. Jeder Kopftreffer senkt sein
Grundtempo dauerhaft (`0,88×` auf Dehşet) und wirft ihn mehrere Sekunden zurück. Nach
allen acht Treffern kriecht er nur noch. Er wird schneller, wenn deine Lampe brennt,
und schneller, wenn du weit weg bist — Abstand ist nie umsonst.

**Licht als Risiko.** Die Taschenlampe zeigt dir den Weg und ihm dich. Die Batterie
läuft leer, flackert vorher und lässt sich mit Fundstücken auffüllen.

**Zwei Meter statt einer Lebensleiste.** *Nefes* ist Ausdauer, *Akıl* ist Verstand.
Akıl sinkt in Dunkelheit und in seiner Nähe und verzerrt Bild und Ton, wenn er kippt.
Wer beim Zupacken keinen Atem mehr hat, kann sich nicht losreißen.

**Türen und Steine.** Eine geschlossene Tür hält ihn ein paar Sekunden auf, dann
splittert sie. Ein geworfener Stein macht dort Lärm, wo er auftrifft, und zieht ihn
für ein paar Sekunden in die falsche Richtung.

**Der Konak.** Prozedural erzeugtes Labyrinth mit ausgeschnittenen Räumen und
zusätzlichen Schleifen — ein perfektes Labyrinth wäre ein Todesurteil, wenn immer
etwas hinter dir ist. Möbliert mit Schränken, Tischen, Kerzen, Kronleuchtern,
verhängten Fenstern, Kilims und Porträts, deren Gesichter fehlen.

**Wetter.** Gewitter beleuchten in unregelmäßigen Abständen für Sekundenbruchteile das
ganze Haus. Manchmal steht er darin.

**Fünf Seiten** eines Reisetagebuchs erzählen, was dem letzten Bewohner passiert ist.

---

## Technik

Kein einziges externes Asset. Alles wird beim Laden erzeugt.

**Texturen** entstehen auf einem 2D-Canvas: Grundfarbe, dazu ein Höhenfeld, aus dem per
Sobel-Operator eine Tangentenraum-Normal-Map und eine Rauheitskarte abgeleitet werden.
Kalkputz, Eichendielen, Bruchsteinboden, anatolischer Kilim, Damasttapete, Rost,
Türholz, Papier.

**Ton** ist vollständig synthetisiert (Web Audio): Herzschlag, Atem, oberflächenabhängige
Schritte, der Schuss aus dem Schalldämpfer als Gasstoß plus zwei Verschlussgeräusche,
Ketten, Donner mit rollender Hüllkurve, Flüstern aus drei Formantfiltern. Der Geist
klingt aus einem `PannerNode` mit HRTF — man hört, aus welcher Richtung er kommt.
Ein aus Rauschen erzeugter Faltungshall gibt dem Haus seine Größe.

**Beleuchtung.** Ein Scheinwerfer für die Lampe wirft Schatten. Alle übrigen Quellen
sind *Emitter*: ein kleiner Pool echter Lichter folgt den nächstgelegenen, sodass 70
Kerzen nur fünf Lichter kosten. Wände, Böden und Decken tragen eine eingebackene
Vertex-Verschattung — Eckenverdunkelung, Schmutz an der Sockelleiste, Ruß unter der
Decke und großflächiges Rauschen, das die Texturkachelung aufbricht.

**Nachbearbeitung.** Eigene Komposition ohne Bibliothekserweiterungen: Schwellenwert-
Bloom über zwei Unschärfestufen, dann ein Durchgang für Linsenverzeichnung, chromatische
Aberration, Unschärfemaskierung, filmische Farbgebung, Vignette, Filmkorn und die
Verzerrung bei niedrigem Akıl. Statt Kantenglättung wird intern höher aufgelöst und
nachgeschärft, was deutlich klarer aussieht.

**Farbraum.** Diese Version der 3D-Bibliothek behandelt Hex-Farben als *lineare* Werte.
Alle Farben im Projekt sind als sRGB geschrieben und werden genau einmal konvertiert
(`GU.linearizeGraph`). Ohne diesen Schritt rendern schwarze Materialien als Mittelgrau
und die ganze Szene wird flach.

### Aufbau

```
index.html            Gerüst, HUD, Menüs
src/style.css         Oberfläche
src/core/util.js      Mathematik, Rauschen, deterministischer Zufall, Farbraum
src/core/textures.js  Prozedurale PBR-Texturen
src/core/audio.js     Synthese und räumlicher Ton
src/core/postfx.js    Bloom und Bildkomposition
src/world/level.js    Labyrinth, Geometrie, Kollision, Wegfindung
src/world/props.js    Türen, Ausgang, Muskalar, Möblierung
src/game/player.js    Eingabe, Bewegung, Nefes und Akıl
src/game/weapon.js    Pistole, Visier, Rückstoß, Ballistik
src/game/ghost.js     Der Gülyabani
src/game/hud.js       Anzeigen, Untertitel, Seiten
src/game/game.js      Welt, Licht, Wetter, Spielschleife
src/main.js           Start, Menüs, Touch
build.js              Bündelt alles in eine Datei
gulyabani_app.py      Streamlit-Hülle
requirements.txt      Streamlit
Start_GULYABANI.bat   Starter für Windows
start_gulyabani.sh    Starter für macOS und Linux
```

### Bauen

```
node build.js
```

Schreibt `dist/gulyabani.html` (vollständiges Dokument) und `dist/embed.html`
(nur Seiteninhalt, für Hosts mit eigenem Dokumentgerüst).

---

## Schwierigkeit

| | Tempo des Geistes | Taumeln nach Treffer | Verlangsamung je Treffer |
|---|---|---|---|
| **Korku** | 2,50 m/s | 7,2 s | ×0,855 |
| **Dehşet** | 2,95 m/s | 6,0 s | ×0,882 |
| **Kâbus** | 3,40 m/s | 4,8 s | ×0,905 |

Zum Vergleich: Gehen 3,05 m/s, Sprinten 5,15 m/s. Auf Dehşet ist er knapp langsamer
als dein Schritt — er holt jedes Mal auf, wenn du stehen bleibst, um zu suchen.

---

Getestet in Chromium, eingebettet und eigenständig. Benötigt WebGL.
