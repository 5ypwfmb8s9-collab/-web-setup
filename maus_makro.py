#!/usr/bin/env python3
"""
Maus-Makro: nimmt eine Abfolge von Mausbewegungen und Klicks auf
und spielt sie beliebig oft immer gleich ab.

Installation:
    pip install pyautogui

Benutzung:
    python maus_makro.py aufnehmen          # Schritte aufnehmen -> makro.json
    python maus_makro.py abspielen          # einmal abspielen
    python maus_makro.py abspielen -n 10    # 10x wiederholen
    python maus_makro.py abspielen -n 0     # endlos wiederholen (Strg+C zum Stoppen)

NOTAUS: Maus schnell in die linke obere Bildschirmecke bewegen
        -> das Skript bricht sofort ab.
"""

import argparse
import json
import sys
import time

try:
    import pyautogui
except ImportError:
    sys.exit("Bitte zuerst installieren:  pip install pyautogui")

pyautogui.FAILSAFE = True  # Maus in Ecke oben links = Abbruch

AKTIONEN = {
    "l": "linksklick",
    "r": "rechtsklick",
    "d": "doppelklick",
    "b": "bewegen",
    "w": "warten",
}


def aufnehmen(datei: str) -> None:
    print("=== Aufnahme ===")
    print("Bewege die Maus an die gewünschte Stelle, dann tippe hier im")
    print("Terminal einen Buchstaben und drücke Enter:")
    print("  l = Linksklick   r = Rechtsklick   d = Doppelklick")
    print("  b = nur hinbewegen   w = Pause einfügen   f = fertig\n")

    schritte = []
    while True:
        wahl = input(f"Schritt {len(schritte) + 1} [l/r/d/b/w/f]: ").strip().lower()
        if wahl == "f":
            break
        if wahl not in AKTIONEN:
            print("  Unbekannt, bitte l, r, d, b, w oder f eingeben.")
            continue

        if wahl == "w":
            sek = float(input("  Wie viele Sekunden warten? ") or 1)
            schritte.append({"aktion": "warten", "sekunden": sek})
            print(f"  -> Pause {sek}s gespeichert")
            continue

        x, y = pyautogui.position()
        schritte.append({"aktion": AKTIONEN[wahl], "x": x, "y": y})
        print(f"  -> {AKTIONEN[wahl]} bei ({x}, {y}) gespeichert")

    with open(datei, "w", encoding="utf-8") as f:
        json.dump(schritte, f, indent=2, ensure_ascii=False)
    print(f"\n{len(schritte)} Schritte in '{datei}' gespeichert.")


def ein_durchlauf(schritte, dauer: float, pause: float) -> None:
    for s in schritte:
        a = s["aktion"]
        if a == "warten":
            time.sleep(s["sekunden"])
            continue
        pyautogui.moveTo(s["x"], s["y"], duration=dauer)
        if a == "linksklick":
            pyautogui.click()
        elif a == "rechtsklick":
            pyautogui.rightClick()
        elif a == "doppelklick":
            pyautogui.doubleClick()
        time.sleep(pause)


def abspielen(datei: str, wiederholungen: int, dauer: float, pause: float,
              start: float) -> None:
    try:
        with open(datei, encoding="utf-8") as f:
            schritte = json.load(f)
    except FileNotFoundError:
        sys.exit(f"'{datei}' nicht gefunden. Erst 'aufnehmen' ausführen.")

    print(f"Starte in {start:g} Sekunden ... (Notaus: Maus in Ecke oben links)")
    time.sleep(start)

    runde = 0
    try:
        while wiederholungen == 0 or runde < wiederholungen:
            runde += 1
            gesamt = "∞" if wiederholungen == 0 else wiederholungen
            print(f"Durchlauf {runde}/{gesamt}")
            ein_durchlauf(schritte, dauer, pause)
    except pyautogui.FailSafeException:
        print("\nNotaus ausgelöst – abgebrochen.")
    except KeyboardInterrupt:
        print("\nMit Strg+C gestoppt.")


def main() -> None:
    p = argparse.ArgumentParser(description="Maus-Bewegungen & Klicks aufnehmen und wiederholen")
    sub = p.add_subparsers(dest="modus", required=True)

    a = sub.add_parser("aufnehmen", help="Schritte aufnehmen")
    a.add_argument("-f", "--datei", default="makro.json")

    s = sub.add_parser("abspielen", help="Aufgenommene Schritte abspielen")
    s.add_argument("-f", "--datei", default="makro.json")
    s.add_argument("-n", "--wiederholungen", type=int, default=1,
                   help="Anzahl Durchläufe, 0 = endlos (Standard: 1)")
    s.add_argument("--dauer", type=float, default=0.3,
                   help="Sekunden pro Mausbewegung (Standard: 0.3)")
    s.add_argument("--pause", type=float, default=0.5,
                   help="Pause nach jedem Schritt in Sekunden (Standard: 0.5)")
    s.add_argument("--start", type=float, default=3,
                   help="Wartezeit vor dem Start in Sekunden (Standard: 3)")

    args = p.parse_args()
    if args.modus == "aufnehmen":
        aufnehmen(args.datei)
    else:
        abspielen(args.datei, args.wiederholungen, args.dauer, args.pause, args.start)


if __name__ == "__main__":
    main()
