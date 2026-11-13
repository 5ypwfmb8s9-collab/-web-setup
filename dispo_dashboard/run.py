"""
Variante A – Ordner (empfohlen für den täglichen Lauf): nimmt je Quelle automatisch die NEUESTE Datei.

    python -m dispo_dashboard.run --ordner "P:/Dispo/SAP_Exporte"

Variante B – Dateien einzeln angeben:

    python -m dispo_dashboard.run --bedarf EXPORT_Bedarf.xlsx --bestand EXPORT_Bestand.xlsx
                                  --zugang ZMM1000.xlsx [--stockreport 28.09_Stok_Raporu.xlsx]

Optionen: --stichtag JJJJ-MM-TT (sonst Datum des Bedarfsexports), --ziel Report.xlsx
Erkennung der Dateien erfolgt über die Spalten, nicht über den Namen.
Datenstand: SAP-Name EXPORT_JJJJMMTT_hhmmss, sonst TT.MM am Namensanfang, sonst Änderungsdatum der Datei.
"""
import argparse
from datetime import datetime
from pathlib import Path

from . import config, excel_report, loaders, logic

QUELLEN = [("bedarf", "Bedarf (Lieferplan-Einteilungen)"), ("bestand", "Bestand (EWM)"),
           ("zugang", "Zugänge (ZMM1000)"), ("stockreport", "Stock Report Versender (nur Info)")]


def main():
    ap = argparse.ArgumentParser(description="Dispo-Auswertung aus SAP-Exporten")
    ap.add_argument("--ordner", help="Ordner mit SAP-Exporten; neueste Datei je Quelle wird genommen")
    ap.add_argument("--bedarf")
    ap.add_argument("--bestand")
    ap.add_argument("--zugang")
    ap.add_argument("--stockreport")
    ap.add_argument("--stichtag", help="JJJJ-MM-TT")
    ap.add_argument("--ziel", help="Ausgabedatei .xlsx")
    a = ap.parse_args()

    dateien = {}
    if a.ordner:
        dateien = {t: p for t, (p, _) in loaders.neueste_dateien(a.ordner).items()}
    for typ in ["bedarf", "bestand", "zugang", "stockreport"]:
        if getattr(a, typ):
            dateien[typ] = Path(getattr(a, typ))
    fehlend = [t for t in ["bedarf", "bestand", "zugang"] if t not in dateien]
    if fehlend:
        raise SystemExit(f"Es fehlen Dateien für: {', '.join(fehlend)}")

    st = (datetime.strptime(a.stichtag, "%Y-%m-%d").date() if a.stichtag
          else loaders.datum_der_datei(dateien["bedarf"]))
    datenstand = [(label, loaders.datum_der_datei(dateien[t], st), Path(dateien[t]).name)
                  for t, label in QUELLEN if t in dateien]

    bedarf = loaders.lade_bedarf(dateien["bedarf"])
    _, bestand_artikel = loaders.lade_bestand(dateien["bestand"])
    zugang = loaders.lade_zugang(dateien["zugang"])
    stockreport = loaders.lade_stockreport(dateien["stockreport"]) if "stockreport" in dateien else None
    positionen, artikel, _ = logic.berechne(bedarf, bestand_artikel, zugang, st)

    ziel = a.ziel or str(Path(a.ordner or ".") / f"Dispo_Auswertung_{st:%Y%m%d}.xlsx")
    excel_report.erstelle(bedarf, bestand_artikel, zugang, artikel, st, ziel, datenstand, stockreport)

    print(f"Stichtag {st:%d.%m.%Y} -> {ziel}")
    for q, d, n in datenstand:
        hinweis = "  <- veraltet" if (st - d).days >= config.QUELLE_VERALTET_TAGE else ""
        print(f"  {q:38} {d:%d.%m.%Y}  {n}{hinweis}")
    print(positionen["Status"].value_counts().to_string())
    print(artikel["Ampel"].value_counts().to_string())


if __name__ == "__main__":
    main()
