"""EDI-Veraenderung: vergleicht zwei Bedarfsexporte (Vortag <-> heute).

Der Kunde schickt seine Lieferabrufe per EDI; SAP schreibt sie in die
Lieferplan-Einteilungen. Wer jeden Tag den Bedarfsexport zieht, kann aus zwei
aufeinanderfolgenden Exporten ablesen, was der Kunde geaendert hat:

  Erhoehung            mehr Menge (bestehende oder neue Einteilung)
  Vorgezogen           Menge auf einen frueheren Termin gelegt
  Neuer Lieferplan     Lieferplan (Artikel/Abladestelle) neu im Abruf
  Nach hinten verschoben  Menge auf einen spaeteren Termin gelegt
  Reduziert / rausgenommen  weniger Menge oder Einteilung gestrichen
  Lieferplan entfallen alle Einteilungen eines Lieferplans weg
  Weggefallen - versendet?  Einteilung der naechsten Tage vorne weg: von uns
                       vorab versendet oder vom Kunden gestrichen (nicht
                       unterscheidbar - wird angezeigt, aber nicht gemailt)
  Versendet / erledigt keine EDI-Aenderung: vorne weggefallene Menge, die wir
                       (vermutlich) versendet haben

Verglichen wird je Lieferplan die OFFENE Menge (Bestellmenge - Geliefert) je
Ladedatum. Die offene Menge aendert sich nur durch zwei Dinge: durch unseren
Versand (immer von vorne, die aeltesten Einteilungen zuerst - FIFO) und durch
den Kunden (EDI). Wareneingaenge beim Kunden aendern sie nicht.

Ablauf je Lieferplan:
  1. Ladedaten bis zum neuen Stichtag zaehlen als "sofort" (Rueckstand) -
     ein Rueckstand, der nur umdatiert wird, ist keine Aenderung.
  2. Differenz je Termin: neu - alt.
  3. Rueckstand / heute faellig weggefallen -> versendet / erledigt
     (unser Versand nimmt immer von vorne weg).
  4. Gleiche Menge an einem Termin weg und an einem anderen dazu ->
     Verschiebung (vorgezogen bzw. nach hinten).
  4b. Danach noch vorne fehlende Menge (naechste ERLEDIGT_VORLAUF_TAGE Tage)
     -> "Weggefallen - versendet?": von uns vorab versendet oder vom Kunden
     gestrichen; wird angezeigt, aber nicht als EDI-Aenderung gemailt.
  5. Restliche Plus- und Minusmengen werden nach naechstem Termin zu
     Verschiebungen gepaart; was uebrig bleibt, ist Erhoehung bzw. Reduzierung.
Verglichen wird nur bis zum letzten Ladedatum, das beide Exporte abdecken
(sonst saehe jeder neue Tag am Ende des Exports wie eine Erhoehung aus).

Rechnet nur mit den Spalten von loaders.lade_bedarf und - fuer die Bewertung -
der Fehlmenge aus logic.berechne; die Dispositionslogik bleibt unveraendert.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from dispo_dashboard import loaders

DISPO_CC = "Dispo@normgmbh.de"
# Empfaenger je Kundenwerk (Spalte "Werk" im Bedarfsexport), z. B.
# {"11": "abruf.wolfsburg@kunde.de; kollege@kunde.de"}. Leer = Empfaenger
# traegt der Disponent in Outlook selbst ein.
EDI_EMPFAENGER: dict[str, str] = {}

ERLEDIGT_VORLAUF_TAGE = 3    # so weit voraus kann vorgezogener Versand vorne Menge wegnehmen
STANDARD_REAKTION_TAGE = 14  # Erhoehung/Vorziehung bis dahin = kurzfristig
RAND_TAGE = 7                # Verschiebung ueber das Ende des Vergleichszeitraums hinaus erkennen
MAILTO_MAX_ZEICHEN = 1900    # laengere mailto-Links schneiden manche Mailprogramme ab

KATEGORIEN = {
    # Reihenfolge = Anzeige-Reihenfolge
    "erhoehung": {"de": "Erhöhung", "en": "Increase", "icon": "⬆️", "farbe": "#dc2626",
                  "hilfe": "Menge erhöht oder neue Einteilung"},
    "vorgezogen": {"de": "Vorgezogen", "en": "Pulled forward", "icon": "⏪", "farbe": "#ea580c",
                   "hilfe": "Menge auf einen früheren Termin gelegt"},
    "neu": {"de": "Neuer Lieferplan", "en": "New schedule", "icon": "🆕", "farbe": "#7c3aed",
            "hilfe": "Artikel/Abladestelle neu im Abruf"},
    "verschoben": {"de": "Nach hinten verschoben", "en": "Postponed", "icon": "⏩", "farbe": "#2563eb",
                   "hilfe": "Menge auf einen späteren Termin gelegt"},
    "reduziert": {"de": "Reduziert / rausgenommen", "en": "Reduced / removed", "icon": "⬇️", "farbe": "#0891b2",
                  "hilfe": "weniger Menge oder Einteilung gestrichen"},
    "entfallen": {"de": "Lieferplan entfallen", "en": "Schedule cancelled", "icon": "❌", "farbe": "#475569",
                  "hilfe": "alle offenen Einteilungen des Lieferplans weg"},
    "unklar": {"de": "Weggefallen – versendet?", "en": "Removed – shipped?", "icon": "❔", "farbe": "#a16207",
               "hilfe": "Einteilung der nächsten Tage vorne weg: von uns vorab versendet – oder vom Kunden gestrichen"},
    "versendet": {"de": "Versendet / erledigt", "en": "Shipped", "icon": "✔️", "farbe": "#16a34a",
                  "hilfe": "vorne weggefallen – meist durch unseren Versand (keine EDI-Änderung)"},
}
MEHR = ("erhoehung", "vorgezogen", "neu")          # Kunde braucht mehr / frueher -> reagieren
WENIGER = ("verschoben", "reduziert", "entfallen")  # Kunde braucht weniger / spaeter

BEWERTUNG = {
    1: "🔴 Handeln",     # mehr/frueher in der Reaktionszeit und jetzt Fehlmenge
    2: "🟠 Prüfen",      # mehr/frueher in der Reaktionszeit oder mit Fehlmenge
    3: "🔵 Info",        # spaetere Erhoehung (gedeckt) oder weniger/spaeter
    4: "✔️ Versendet",   # nur versendet, keine EDI-Aenderung
}

_EPS = 1e-6


# --- Dateien ------------------------------------------------------------------

def finde_vortag_datei(ordner, stichtag):
    """Neuester Bedarfsexport im Ordner mit Datenstand VOR dem Stichtag
    (Vortag, nach Wochenende/Feiertag der letzte Arbeitstag).
    Rueckgabe (Pfad, Datum) oder None."""
    if not ordner:
        return None
    st = pd.Timestamp(stichtag).date()
    beste = None
    for p in sorted(Path(ordner).glob("*.xls*")):
        if p.name.startswith("~$") or p.name.startswith("Dispo_Auswertung"):
            continue
        d = loaders.datum_der_datei(p)
        if d >= st or loaders.dateityp(p) != "bedarf":
            continue
        schluessel = (d, p.stat().st_mtime)
        if beste is None or schluessel > beste[2]:
            beste = (p, d, schluessel)
    return (beste[0], beste[1]) if beste else None


def datum_aus_name(name: str):
    """Datenstand aus dem SAP-Dateinamen (EXPORT_JJJJMMTT_hhmmss) oder None."""
    m = re.search(r"(\d{8})_\d{6}", str(name))
    return pd.Timestamp(m.group(1)).date() if m else None


# --- Hilfen -----------------------------------------------------------------------

def kundenteil(kundenmaterial) -> str:
    """Kundenmaterial lesbar: '-N---910-971-02' -> 'N 910 971 02'."""
    text = str(kundenmaterial or "").strip()
    return re.sub(r"-+", " ", text).strip()


def _menge(wert) -> str:
    return f"{float(wert):,.0f}".replace(",", ".")


def _datum(wert) -> str:
    return pd.Timestamp(wert).strftime("%d.%m.%Y")


def _vorbereiten(bedarf: pd.DataFrame | None) -> pd.DataFrame:
    spalten = ["Lieferplan", "Norm-Nr", "Kunde", "Werk", "Abladestelle", "Kundenmaterial", "Kurztext",
               "Ladedatum", "Wunschtermin", "Offen"]
    if bedarf is None or bedarf.empty:
        return pd.DataFrame(columns=spalten)
    df = bedarf.copy()
    df["Offen"] = (pd.to_numeric(df["Bestellmenge"], errors="coerce").fillna(0)
                   - pd.to_numeric(df["Geliefert"], errors="coerce").fillna(0)).clip(lower=0)
    df["Ladedatum"] = pd.to_datetime(df["Ladedatum"]).dt.normalize()
    df["Wunschtermin"] = pd.to_datetime(df["Wunschtermin"]).dt.normalize()
    for s in ("Kunde", "Werk", "Abladestelle", "Kundenmaterial", "Kurztext"):
        if s not in df.columns:
            df[s] = ""
        df[s] = df[s].fillna("").astype(str)
    df = df[(df["Offen"] > _EPS) & df["Ladedatum"].notna()]
    return df[spalten].reset_index(drop=True)


def _ereignis(kategorie: str, menge: float, datum_alt=None, datum_neu=None, menge_alt=0.0, menge_neu=0.0) -> dict:
    tage = (pd.Timestamp(datum_neu) - pd.Timestamp(datum_alt)).days if datum_alt is not None and datum_neu is not None else None
    return {"Kategorie": kategorie, "Menge": float(menge), "Datum alt": datum_alt, "Datum neu": datum_neu,
            "Menge alt": float(menge_alt), "Menge neu": float(menge_neu), "Tage": tage}


def _verschiebung(menge: float, datum_alt, datum_neu, alt: dict, neu: dict) -> dict:
    kategorie = "vorgezogen" if datum_neu < datum_alt else "verschoben"
    return _ereignis(kategorie, menge, datum_alt, datum_neu, alt.get(datum_alt, 0.0), neu.get(datum_neu, 0.0))


# --- Vergleich je Lieferplan --------------------------------------------------------

def _vergleiche_lieferplan(a: pd.DataFrame, n: pd.DataFrame, st: pd.Timestamp, grenze: pd.Timestamp,
                           vorlauf_tage: int = ERLEDIGT_VORLAUF_TAGE) -> list[dict]:
    """Aenderungen eines Lieferplans (siehe Modul-Doku). a/n = offene Einteilungen
    alt/neu (aus _vorbereiten). Termine bis zum Stichtag zaehlen als Stichtag."""
    def _termin(d):
        return max(pd.Timestamp(d), st)

    alt = a.groupby(a["Ladedatum"].map(_termin))["Offen"].sum().to_dict() if not a.empty else {}
    neu = n.groupby(n["Ladedatum"].map(_termin))["Offen"].sum().to_dict() if not n.empty else {}
    rest = {}
    for d in sorted(set(alt) | set(neu)):
        r = neu.get(d, 0.0) - alt.get(d, 0.0)
        if abs(r) > _EPS:
            rest[d] = r
    ereignisse = []

    # Versand nimmt immer von vorne weg (aelteste Einteilung zuerst). Was vorne
    # fehlt, ist "versendet" - solange davor alles ganz weg ist (FIFO).
    fenster = st + pd.Timedelta(days=vorlauf_tage)
    versand = {"weiter": True}

    def _versand(termine) -> None:
        for d in termine:
            if not versand["weiter"]:
                return
            r = rest.get(d, 0.0)
            if r >= -_EPS:
                versand["weiter"] = False   # unveraendert/erhoeht: dahinter kann Versand nichts wegnehmen
                return
            ereignisse.append(_ereignis("versendet" if d <= st else "unklar", -r, d, None, alt[d], neu.get(d, 0.0)))
            del rest[d]
            if neu.get(d, 0.0) > _EPS:
                versand["weiter"] = False   # nur teilweise weg: dahinter nichts versendet
                return

    # 1. Rueckstand / heute faellig (Termin = Stichtag): was weg ist, ist versendet.
    #    Kommt vor dem Paaren: eine Erhoehung, die zufaellig so gross ist wie die
    #    versendete Menge, darf nicht als Verschiebung untergehen.
    _versand([d for d in sorted(alt) if d <= st])

    # 2. Gleiche Menge weg und woanders dazu (innerhalb des Vergleichszeitraums) -> Verschiebung
    for d_alt in sorted(d for d, r in rest.items() if r < 0 and d <= grenze):
        menge = -rest[d_alt]
        kandidaten = [d for d, r in rest.items() if r > 0 and d <= grenze and abs(r - menge) <= _EPS]
        if not alt or not neu or not kandidaten:
            continue
        d_neu = min(kandidaten, key=lambda d: (abs((d - d_alt).days), d))
        ereignisse.append(_verschiebung(menge, d_alt, d_neu, alt, neu))
        del rest[d_alt], rest[d_neu]

    # 2b. Naechste Tage (vorgezogener Versand durch uns): was jetzt noch vorne
    #     fehlt und keine Verschiebung ist, ist ebenfalls versendet.
    _versand([d for d in sorted(alt) if st < d <= fenster])

    # 3. Restliche Plus/Minus nach naechstem Termin paaren (Teilverschiebungen)
    def _paarbar(d_minus, d_plus) -> bool:
        if d_minus <= grenze and d_plus <= grenze:
            return True
        # ueber das Ende des Vergleichszeitraums hinaus nur am Rand (Verschiebung um wenige Tage)
        return (d_minus <= grenze or d_plus <= grenze) and abs((d_plus - d_minus).days) <= RAND_TAGE

    if alt and neu:
        while True:
            paare = [(abs((dp - dm).days), dm, dp) for dm, rm in rest.items() if rm < 0
                     for dp, rp in rest.items() if rp > 0 and _paarbar(dm, dp)]
            if not paare:
                break
            _, dm, dp = min(paare)
            menge = min(-rest[dm], rest[dp])
            ereignisse.append(_verschiebung(menge, dm, dp, alt, neu))
            for d, delta in ((dm, menge), (dp, -menge)):
                rest[d] += delta
                if abs(rest[d]) <= _EPS:
                    del rest[d]

    # 4. Uebrig: Erhoehung / Reduzierung (nur innerhalb des Vergleichszeitraums)
    for d, r in sorted(rest.items()):
        if d > grenze:
            continue
        if r > 0:
            kategorie = "neu" if a.empty else "erhoehung"
            ereignisse.append(_ereignis(kategorie, r, None, d, alt.get(d, 0.0), neu.get(d, 0.0)))
        else:
            kategorie = "entfallen" if n.empty else "reduziert"
            ereignisse.append(_ereignis(kategorie, -r, d, None, alt.get(d, 0.0), neu.get(d, 0.0)))
    return ereignisse


def _ereignis_text(e: dict, st: pd.Timestamp) -> str:
    def _t(d):
        return "sofort (Rückstand)" if pd.Timestamp(d) <= st else _datum(d)

    k, m = e["Kategorie"], _menge(e["Menge"])
    if k in ("vorgezogen", "verschoben"):
        richtung = "früher" if k == "vorgezogen" else "später"
        tage = abs(int(e["Tage"]))
        return (f"{m} Stück von {_t(e['Datum alt'])} auf {_t(e['Datum neu'])} "
                f"({tage} {'Tag' if tage == 1 else 'Tage'} {richtung})")
    if k in ("erhoehung", "neu"):
        if e["Menge alt"] > _EPS:
            return f"{_t(e['Datum neu'])}: +{m} Stück ({_menge(e['Menge alt'])} → {_menge(e['Menge neu'])})"
        return f"{_t(e['Datum neu'])}: +{m} Stück (neue Einteilung)"
    if k in ("reduziert", "entfallen"):
        if e["Menge neu"] > _EPS:
            return f"{_t(e['Datum alt'])}: −{m} Stück ({_menge(e['Menge alt'])} → {_menge(e['Menge neu'])})"
        return f"{_t(e['Datum alt'])}: −{m} Stück (Einteilung gestrichen)"
    if k == "unklar":
        return f"{_t(e['Datum alt'])}: {m} Stück weg – vorab versendet? Sonst vom Kunden gestrichen"
    return f"{_t(e['Datum alt'])}: {m} Stück weg (vermutlich versendet)"


# --- Gesamtvergleich ------------------------------------------------------------------

def vergleiche(bedarf_alt: pd.DataFrame, bedarf_neu: pd.DataFrame, stichtag_alt, stichtag_neu,
               positionen_neu: pd.DataFrame | None = None, reaktion_tage: int = STANDARD_REAKTION_TAGE,
               vorlauf_tage: int = ERLEDIGT_VORLAUF_TAGE) -> dict:
    """Vergleicht zwei Bedarfsexporte. positionen_neu (optional) = Ergebnis von
    logic.berechne fuer den neuen Stand - liefert die Fehlmenge je Lieferplan
    fuer die Bewertung. Rueckgabe-dict:
      ereignisse   DataFrame je Aenderung (Kategorie, Termine, Mengen, Text)
      lieferplaene DataFrame je Lieferplan mit Aenderung (Bewertung, Mengen je
                   Kategorie, Fehlmenge, Details), dringendste zuerst
      kurven       {Lieferplan: {"alt": {Termin: Menge}, "neu": {...}}}
      zusammenfassung {Kategorie: {"lieferplaene": n, "menge": m}}
      grenze, stichtag_alt, stichtag_neu, reaktion_tage, ausserhalb (neue
      Menge nach dem Vergleichszeitraum, nicht bewertet)."""
    st_alt = pd.Timestamp(stichtag_alt).normalize()
    st = pd.Timestamp(stichtag_neu).normalize()
    a, n = _vorbereiten(bedarf_alt), _vorbereiten(bedarf_neu)
    maxima = [df["Ladedatum"].max() for df in (a, n) if not df.empty]
    grenze = max(min(maxima), st) if maxima else st

    stamm = pd.concat([n, a]).drop_duplicates("Lieferplan").set_index("Lieferplan")
    versatz = (pd.concat([n, a]).assign(_v=lambda d: (d["Wunschtermin"] - d["Ladedatum"]).dt.days)
               .groupby("Lieferplan")["_v"].median()) if len(stamm) else pd.Series(dtype=float)

    ereignisse, kurven = [], {}
    a_je = {lp: g for lp, g in a.groupby("Lieferplan")}
    n_je = {lp: g for lp, g in n.groupby("Lieferplan")}
    leer = a.iloc[0:0]
    for lp in sorted(set(a_je) | set(n_je), key=str):
        ga, gn = a_je.get(lp, leer), n_je.get(lp, leer)
        liste = _vergleiche_lieferplan(ga, gn, st, grenze, vorlauf_tage)
        if not liste:
            continue
        for e in liste:
            e["Lieferplan"] = lp
            e["Text"] = _ereignis_text(e, st)
        ereignisse.extend(liste)

        def _termin(d):
            return max(pd.Timestamp(d), st)
        kurven[lp] = {
            "alt": ga.groupby(ga["Ladedatum"].map(_termin))["Offen"].sum().to_dict() if not ga.empty else {},
            "neu": gn.groupby(gn["Ladedatum"].map(_termin))["Offen"].sum().to_dict() if not gn.empty else {},
        }

    spalten_e = ["Lieferplan", "Kategorie", "Menge", "Datum alt", "Datum neu", "Menge alt", "Menge neu", "Tage", "Text"]
    ev = pd.DataFrame(ereignisse, columns=spalten_e) if ereignisse else pd.DataFrame(columns=spalten_e)
    reihenfolge = {k: i for i, k in enumerate(KATEGORIEN)}
    if not ev.empty:
        ev["Termin"] = ev["Datum neu"].fillna(ev["Datum alt"])
        ev = ev.assign(_k=ev["Kategorie"].map(reihenfolge)).sort_values(
            ["Lieferplan", "_k", "Termin"], kind="stable").drop(columns="_k").reset_index(drop=True)
        for s in ("Norm-Nr", "Kunde", "Werk", "Abladestelle", "Kundenmaterial", "Kurztext"):
            ev[s] = ev["Lieferplan"].map(stamm[s])
        ev["Versatz"] = ev["Lieferplan"].map(versatz).fillna(0)
    else:
        ev["Termin"] = pd.Series(dtype="datetime64[ns]")

    # Fehlmenge je Lieferplan im neuen Stand (aus logic.berechne)
    fehl, fehltag = {}, {}
    if positionen_neu is not None and not positionen_neu.empty and "Lieferplan" in positionen_neu.columns:
        mit_fehl = positionen_neu[pd.to_numeric(positionen_neu["Fehlmenge"], errors="coerce").fillna(0) > 0]
        fehl = mit_fehl.groupby("Lieferplan")["Fehlmenge"].sum().to_dict()
        fehltag = mit_fehl.groupby("Lieferplan")["Ladedatum"].min().to_dict()

    grenze_kurz = st + pd.Timedelta(days=int(reaktion_tage))
    zeilen = []
    for lp, g in ev.groupby("Lieferplan", sort=False):
        summe = {k: float(g.loc[g["Kategorie"] == k, "Menge"].sum()) for k in KATEGORIEN}
        kategorien = [k for k in KATEGORIEN if summe[k] > _EPS]
        mehr_ev = g[g["Kategorie"].isin(MEHR)]
        echte = g[~g["Kategorie"].isin(["versendet", "unklar"])]
        anzeigen = g[g["Kategorie"] != "versendet"]
        erster_mehr = mehr_ev["Datum neu"].min() if not mehr_ev.empty else pd.NaT
        f = float(fehl.get(lp, 0.0))
        kurzfristig = pd.notna(erster_mehr) and erster_mehr <= grenze_kurz
        if echte.empty:
            # nur weggefallen: Rueckstand = versendet (ausblenden); naechste Tage = unklar -> zeigen
            rang = 3 if (g["Kategorie"] == "unklar").any() else 4
        elif not mehr_ev.empty and kurzfristig and f > 0:
            rang = 1
        elif not mehr_ev.empty and (kurzfristig or f > 0):
            rang = 2
        else:
            rang = 3
        s = stamm.loc[lp]
        zeilen.append({
            "Rang": rang,
            "Bewertung": BEWERTUNG[rang],
            "Änderung": " · ".join(f"{KATEGORIEN[k]['icon']} {KATEGORIEN[k]['de']}" for k in kategorien),
            "Kategorien": kategorien,
            "Lieferplan": lp,
            "Norm-Nr": s["Norm-Nr"],
            "Teil (Kunde)": kundenteil(s["Kundenmaterial"]),
            "Kurztext": s["Kurztext"],
            "Kunde": s["Kunde"],
            "Werk": s["Werk"],
            "Abladestelle": s["Abladestelle"],
            "Mehr": summe["erhoehung"] + summe["neu"],
            "Vorgezogen": summe["vorgezogen"],
            "Verschoben": summe["verschoben"],
            "Weniger": summe["reduziert"] + summe["entfallen"],
            "Versendet": summe["versendet"],
            "Netto": summe["erhoehung"] + summe["neu"] - summe["reduziert"] - summe["entfallen"],
            "Erster Termin": anzeigen["Termin"].min() if not anzeigen.empty else pd.NaT,
            "Erste Mehrmenge": erster_mehr,
            "Fehlmenge": f,
            "Erster Fehltag": fehltag.get(lp, pd.NaT),
            "Details": " | ".join(f"{KATEGORIEN[k]['icon']} {t}" for k, t in zip(anzeigen["Kategorie"], anzeigen["Text"]))
                       or " | ".join(f"{KATEGORIEN['versendet']['icon']} {t}" for t in g["Text"]),
        })
    spalten_l = ["Rang", "Bewertung", "Änderung", "Kategorien", "Lieferplan", "Norm-Nr", "Teil (Kunde)", "Kurztext",
                 "Kunde", "Werk", "Abladestelle", "Mehr", "Vorgezogen", "Verschoben", "Weniger", "Versendet", "Netto",
                 "Erster Termin", "Erste Mehrmenge", "Fehlmenge", "Erster Fehltag", "Details"]
    lp_df = pd.DataFrame(zeilen, columns=spalten_l)
    if not lp_df.empty:
        lp_df = lp_df.assign(_m=lp_df["Mehr"] + lp_df["Vorgezogen"]).sort_values(
            ["Rang", "Erste Mehrmenge", "Erster Termin", "_m"], ascending=[True, True, True, False],
            na_position="last", kind="stable").drop(columns="_m").reset_index(drop=True)

    zusammenfassung = {
        k: {"lieferplaene": int(ev.loc[ev["Kategorie"] == k, "Lieferplan"].nunique()) if not ev.empty else 0,
            "menge": float(ev.loc[ev["Kategorie"] == k, "Menge"].sum()) if not ev.empty else 0.0}
        for k in KATEGORIEN
    }
    ausserhalb = float(n.loc[n["Ladedatum"] > grenze, "Offen"].sum()) if not n.empty else 0.0
    return {
        "ereignisse": ev,
        "lieferplaene": lp_df,
        "kurven": kurven,
        "zusammenfassung": zusammenfassung,
        "grenze": grenze,
        "stichtag_alt": st_alt,
        "stichtag_neu": st,
        "reaktion_tage": int(reaktion_tage),
        "ausserhalb": ausserhalb,
        "anzahl_lieferplaene": int(len(set(a["Lieferplan"]) | set(n["Lieferplan"]))),
    }


# --- E-Mail-Vorlage ---------------------------------------------------------------------

_MAIL = {
    "DE": {
        "betreff": "Abrufänderung {kunde} – Teil {teil} – {arten}",
        "betreff_sammel": "Abrufänderungen {kunde} {werk} – {anzahl} Teile",
        "anrede": "Sehr geehrte Damen und Herren,",
        "einleitung": "im aktuellen Lieferabruf vom {neu} haben sich gegenüber dem Abruf vom {alt} folgende "
                      "Änderungen ergeben:",
        "teil": "Teil {teil}{text} · unsere Nr. {norm}",
        "ort": "Lieferplan {lp} · Werk {werk} · Abladestelle {abl}",
        "termin": "Liefertermin",
        "sofort": "sofort (Rückstand)",
        "erhoehung": "Erhöhung: {termin} {t} – {alt} → {neu} Stück (+{m})",
        "erhoehung_neu": "Neue Einteilung: {termin} {t} – {m} Stück",
        "neu": "Neuer Abruf: {termin} {t} – {m} Stück",
        "vorgezogen": "Vorgezogen: {m} Stück von {ta} auf {tn} ({tage} {tage_wort} früher)",
        "verschoben": "Verschoben: {m} Stück von {ta} auf {tn} ({tage} {tage_wort} später)",
        "tag": "Tag", "tage": "Tage",
        "reduziert": "Reduziert: {termin} {t} – {alt} → {neu} Stück (−{m})",
        "reduziert_weg": "Gestrichen: {termin} {t} – {m} Stück",
        "entfallen": "Entfallen: {termin} {t} – {m} Stück",
        "was": {"erhoehung": "die Mehrmenge", "vorgezogen": "die Vorziehung", "neu": "den neuen Abruf"},
        "kritisch": "{was} können wir nach aktuellem Stand nicht vollständig "
                    "termingerecht liefern. Wir prüfen alle Möglichkeiten und melden uns schnellstmöglich mit einem "
                    "Liefervorschlag. Bitte prüfen Sie, ob die Änderung in dieser Form benötigt wird und ob eine "
                    "Teillieferung möglich ist.",
        "pruefen": "Wir prüfen die Umsetzung und melden uns kurzfristig. Bitte bestätigen Sie uns, dass die Änderung "
                   "so beabsichtigt ist.",
        "gedeckt": "Nach aktuellem Stand können wir die geänderten Mengen zum gewünschten Termin liefern. Bitte "
                   "bestätigen Sie uns kurz, dass die Änderung so beabsichtigt ist.",
        "weniger": "Bitte bestätigen Sie uns, dass die Reduzierung bzw. Terminverschiebung so beabsichtigt ist – "
                   "die Ware ist bei uns bereits disponiert.",
        "weniger_auch": "Bitte bestätigen Sie außerdem die Reduzierung bzw. Terminverschiebung.",
        "gruss": "Mit freundlichen Grüßen",
        "gekuerzt": "… sowie {n} weitere Änderungen (Liste folgt / siehe Anhang)",
    },
    "EN": {
        "betreff": "Delivery schedule change {kunde} – part {teil} – {arten}",
        "betreff_sammel": "Delivery schedule changes {kunde} {werk} – {anzahl} parts",
        "anrede": "Dear Sir or Madam,",
        "einleitung": "your current delivery schedule of {neu} contains the following changes compared to the "
                      "schedule of {alt}:",
        "teil": "Part {teil}{text} · our no. {norm}",
        "ort": "Scheduling agreement {lp} · plant {werk} · unloading point {abl}",
        "termin": "delivery date",
        "sofort": "immediately (backlog)",
        "erhoehung": "Increase: {termin} {t} – {alt} → {neu} pcs (+{m})",
        "erhoehung_neu": "New schedule line: {termin} {t} – {m} pcs",
        "neu": "New schedule: {termin} {t} – {m} pcs",
        "vorgezogen": "Pulled forward: {m} pcs from {ta} to {tn} ({tage} {tage_wort} earlier)",
        "verschoben": "Postponed: {m} pcs from {ta} to {tn} ({tage} {tage_wort} later)",
        "tag": "day", "tage": "days",
        "reduziert": "Reduced: {termin} {t} – {alt} → {neu} pcs (−{m})",
        "reduziert_weg": "Cancelled: {termin} {t} – {m} pcs",
        "entfallen": "Cancelled: {termin} {t} – {m} pcs",
        "was": {"erhoehung": "the additional quantity", "vorgezogen": "the earlier date", "neu": "the new schedule"},
        "kritisch": "Based on our current stock we cannot supply {was} completely on "
                    "time. We are checking all options and will come back to you with a delivery proposal as soon "
                    "as possible. Please check whether the change is required in this form and whether a partial "
                    "delivery is possible.",
        "pruefen": "We are checking the implementation and will get back to you shortly. Please confirm that the "
                   "change is intended.",
        "gedeckt": "Based on our current stock we can deliver the changed quantities on the requested date. Please "
                   "confirm briefly that the change is intended.",
        "weniger": "Please confirm that the reduction or postponement is intended – the goods have already been "
                   "planned on our side.",
        "weniger_auch": "Please also confirm the reduction or postponement.",
        "gruss": "Kind regards",
        "gekuerzt": "… and {n} further changes (list to follow / see attachment)",
    },
}


def _liefertermin(ladedatum, versatz: float, st: pd.Timestamp, t: dict) -> str:
    """Termin fuer den Kunden: Ladedatum + Versatz (Wunschtermin - Ladedatum)."""
    if pd.Timestamp(ladedatum) <= st:
        return t["sofort"]
    return _datum(pd.Timestamp(ladedatum) + pd.Timedelta(days=float(versatz or 0)))


def _mail_zeilen(g: pd.DataFrame, st: pd.Timestamp, t: dict) -> list[str]:
    zeilen = []
    for e in g.to_dict("records"):
        k = e["Kategorie"]
        if k in ("versendet", "unklar"):
            continue
        v = e["Versatz"]
        werte = {"termin": t["termin"], "m": _menge(e["Menge"]), "alt": _menge(e["Menge alt"]),
                 "neu": _menge(e["Menge neu"]), "tage": abs(int(e["Tage"])) if pd.notna(e["Tage"]) else ""}
        werte["tage_wort"] = t["tag"] if werte["tage"] == 1 else t["tage"]
        if pd.notna(e["Datum neu"]):
            werte["t"] = werte["tn"] = _liefertermin(e["Datum neu"], v, st, t)
        if pd.notna(e["Datum alt"]):
            werte["ta"] = _liefertermin(e["Datum alt"], v, st, t)
            werte.setdefault("t", werte["ta"])
        if k == "erhoehung" and e["Menge alt"] <= _EPS:
            vorlage = t["erhoehung_neu"]
        elif k == "reduziert" and e["Menge neu"] <= _EPS:
            vorlage = t["reduziert_weg"]
        else:
            vorlage = t[k]
        zeilen.append("• " + vorlage.format(**werte))
    return zeilen


def mail_entwurf(ergebnis: dict, lieferplaene: list, sprache: str = "DE") -> dict:
    """E-Mail-Vorlage zu einem oder mehreren Lieferplaenen (z. B. alle eines
    Kundenwerks). Rueckgabe: {"an", "cc", "betreff", "text", "mailto", "gekuerzt"}."""
    t = _MAIL["EN" if str(sprache).upper().startswith("EN") else "DE"]
    st = ergebnis["stichtag_neu"]
    lp_df = ergebnis["lieferplaene"].set_index("Lieferplan")
    ev = ergebnis["ereignisse"]
    lieferplaene = [lp for lp in lieferplaene if lp in lp_df.index]
    if not lieferplaene:
        return {"an": "", "cc": DISPO_CC, "betreff": "", "text": "", "mailto": "", "gekuerzt": False}
    erste = lp_df.loc[lieferplaene[0]]
    werk = str(erste["Werk"] or "")
    kunde = str(erste["Kunde"] or "")

    bloecke, rang, hat_mehr, hat_weniger, arten = [], 4, False, False, []
    for lp in lieferplaene:
        z = lp_df.loc[lp]
        zeilen = _mail_zeilen(ev[ev["Lieferplan"] == lp], st, t)
        if not zeilen:
            continue
        rang = min(rang, int(z["Rang"]))
        hat_mehr |= any(k in MEHR for k in z["Kategorien"])
        hat_weniger |= any(k in WENIGER for k in z["Kategorien"])
        arten += [k for k in z["Kategorien"] if k not in ("versendet", "unklar") and k not in arten]
        text = f" ({z['Kurztext']})" if z["Kurztext"] else ""
        bloecke.append([t["teil"].format(teil=z["Teil (Kunde)"] or z["Norm-Nr"], text=text, norm=z["Norm-Nr"]),
                        t["ort"].format(lp=lp, werk=z["Werk"] or "–", abl=z["Abladestelle"] or "–"), *zeilen])

    if not bloecke:   # nur versendet - keine EDI-Aenderung, keine Mail
        return {"an": "", "cc": DISPO_CC, "betreff": "", "text": "", "mailto": "", "gekuerzt": False}
    if len(lieferplaene) == 1:
        sprachschluessel = "en" if t is _MAIL["EN"] else "de"
        betreff = t["betreff"].format(kunde=kunde, teil=erste["Teil (Kunde)"] or erste["Norm-Nr"],
                                      arten=", ".join(KATEGORIEN[k][sprachschluessel] for k in arten))
    else:
        betreff = t["betreff_sammel"].format(kunde=kunde, werk=f"({werk})" if werk else "", anzahl=len(bloecke))

    was = " bzw. " if t is _MAIL["DE"] else " / "
    was = was.join(t["was"][k] for k in arten if k in MEHR)
    if hat_mehr and rang == 1:
        kritisch = t["kritisch"].format(was=was[:1].upper() + was[1:] if t is _MAIL["DE"] else was)
        schluss = [kritisch] + ([t["weniger_auch"]] if hat_weniger else [])
    elif hat_mehr and rang == 2:
        schluss = [t["pruefen"]] + ([t["weniger_auch"]] if hat_weniger else [])
    elif hat_mehr:
        schluss = [t["gedeckt"]] + ([t["weniger_auch"]] if hat_weniger else [])
    else:
        schluss = [t["weniger"]]

    kopf = [t["anrede"], "", t["einleitung"].format(neu=_datum(st), alt=_datum(ergebnis["stichtag_alt"])), ""]
    fuss = ["", *schluss, "", t["gruss"], ""]

    def _zusammen(anzahl_bloecke: int) -> str:
        teile = list(kopf)
        for b in bloecke[:anzahl_bloecke]:
            teile += b + [""]
        if anzahl_bloecke < len(bloecke):
            teile += [t["gekuerzt"].format(n=len(bloecke) - anzahl_bloecke), ""]
        return "\n".join(teile[:-1] + fuss)

    an = EDI_EMPFAENGER.get(werk, "")
    text = _zusammen(len(bloecke))
    link, gekuerzt = mailto_link(an, DISPO_CC, betreff, text), False
    anzahl = len(bloecke)
    while len(link) > MAILTO_MAX_ZEICHEN and anzahl > 1:
        anzahl -= 1
        link, gekuerzt = mailto_link(an, DISPO_CC, betreff, _zusammen(anzahl)), True
    return {"an": an, "cc": DISPO_CC, "betreff": betreff, "text": text, "mailto": link, "gekuerzt": gekuerzt}


def mailto_link(an: str, cc: str, betreff: str, text: str) -> str:
    """mailto-Link: oeffnet das Standard-Mailprogramm (Outlook) mit Empfaenger,
    CC, Betreff und Text. Zeilenumbrueche als CRLF (wie Outlook sie erwartet)."""
    an = quote((an or "").replace(" ", ""), safe="@;,.")
    teile = [f"cc={quote(cc, safe='@;,.')}"] if cc else []
    teile += [f"subject={quote(betreff, safe='')}", f"body={quote(text.replace(chr(10), chr(13) + chr(10)), safe='')}"]
    return f"mailto:{an}?" + "&".join(teile)


# --- Excel-Export ------------------------------------------------------------------------

def erstelle_excel(ergebnis: dict) -> bytes:
    """Aenderungen als Excel (Archiv / Weitergabe): je Lieferplan und je Aenderung."""
    wb = Workbook()
    kopf_fuellung = PatternFill("solid", fgColor="F1F5F9")
    kopf_schrift = Font(bold=True, color="334155", size=10)
    linie = Border(bottom=Side(style="thin", color="E2E8F0"))
    st = ergebnis["stichtag_neu"]

    def _blatt(ws, titel: str, df: pd.DataFrame, breiten: dict, datum_spalten=(), mengen_spalten=()):
        ws.sheet_view.showGridLines = False
        ws.cell(1, 1, value=titel).font = Font(bold=True, size=14, color="1E293B")
        ws.cell(2, 1, value=f"Abruf vom {_datum(ergebnis['stichtag_alt'])} → {_datum(st)} · verglichen bis Ladedatum "
                            f"{_datum(ergebnis['grenze'])}").font = Font(size=9, color="64748B")
        for i, s in enumerate(df.columns, start=1):
            c = ws.cell(4, i, value=s)
            c.fill, c.font = kopf_fuellung, kopf_schrift
            c.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[get_column_letter(i)].width = breiten.get(s, 12)
        for r, zeile in enumerate(df.itertuples(index=False), start=5):
            for i, wert in enumerate(zeile, start=1):
                if isinstance(wert, float) and pd.isna(wert):
                    wert = None
                elif isinstance(wert, pd.Timestamp):
                    wert = None if pd.isna(wert) else wert.to_pydatetime()
                elif wert is pd.NaT:
                    wert = None
                c = ws.cell(r, i, value=wert)
                c.border = linie
                c.alignment = Alignment(vertical="top", wrap_text=df.columns[i - 1] in ("Details", "Text"))
                if df.columns[i - 1] in datum_spalten:
                    c.number_format = "DD.MM.YYYY"
                elif df.columns[i - 1] in mengen_spalten:
                    c.number_format = '#,##0;-#,##0;""'
        ws.freeze_panes = "A5"
        if len(df):
            ws.auto_filter.ref = f"A4:{get_column_letter(len(df.columns))}{4 + len(df)}"

    lp = ergebnis["lieferplaene"].drop(columns=["Rang", "Kategorien"])
    _blatt(wb.active, "EDI-Veränderung je Lieferplan", lp,
           {"Bewertung": 13, "Änderung": 30, "Teil (Kunde)": 16, "Kurztext": 26, "Kunde": 26, "Details": 80},
           datum_spalten=("Erster Termin", "Erste Mehrmenge", "Erster Fehltag"),
           mengen_spalten=("Mehr", "Vorgezogen", "Verschoben", "Weniger", "Versendet", "Netto", "Fehlmenge"))
    wb.active.title = "Je Lieferplan"
    ev = ergebnis["ereignisse"]
    if not ev.empty:
        ev = ev.assign(Kategorie=ev["Kategorie"].map(lambda k: KATEGORIEN[k]["de"]))
        ev = ev[["Kategorie", "Norm-Nr", "Kundenmaterial", "Kunde", "Werk", "Abladestelle", "Lieferplan",
                 "Datum alt", "Datum neu", "Menge", "Menge alt", "Menge neu", "Tage", "Text"]]
    _blatt(wb.create_sheet("Alle Änderungen"), "Alle Änderungen (je Termin)", ev,
           {"Kategorie": 22, "Kunde": 26, "Text": 60, "Kundenmaterial": 16},
           datum_spalten=("Datum alt", "Datum neu"), mengen_spalten=("Menge", "Menge alt", "Menge neu"))
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def dateiname(stichtag) -> str:
    return f"EDI_Veraenderung_{pd.Timestamp(stichtag):%Y%m%d}.xlsx"
