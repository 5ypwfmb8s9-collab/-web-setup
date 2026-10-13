"""Planung Erstellung: taegliche Kommissionier-/Palettenplanung fuer VW aus
Kundenauftraegen (Dashboard Dispo: Bedarf) und Bestand erzeugen.

Nutzt die vom Kunden bereitgestellte Excel-Vorlage (dispo_dashboard/
planung_vorlage.xlsx, alle 17 Blaetter inkl. Referenzdaten/Formeln bleiben
unveraendert) und befuellt nur die hellgrauen Eingabespalten in den
Blaettern "Almanca" (Hauptplanung), "Rueckstaende" und "DHL UPS".

Datengrundlage: dieselben positionen wie im Dashboard Dispo (Bedarf +
Bestand, bereits mit Fehlmenge/Status berechnet) - kein erneuter Upload
noetig, Dispo muss vorher geladen sein.

Geschaeftslogik (siehe Anfrage, anhand der Vorlage/Formeln verifiziert):
- Kundenauftraege vom aeltesten Ladedatum bis zum gewaehlten Planungsdatum.
- Fehlmenge > 0 (nicht gedeckt) -> Blatt "Rueckstaende", rote Schrift.
- Fehlmenge <= 0 (Bestand reicht) -> Blatt "Almanca": Spalte C "Lagerort"
  = Abladestelle aus dem Kundenauftrag (per echten Daten verifiziert:
  Dispo-Abladestelle entspricht hier der Vorlagen-Spalte "Lagerort", NICHT
  der Vorlagen-Spalte "Abladestelle" - letztere wird aus einer anderen
  Codierung ueber das Blatt "Werke" abgeleitet), Spalte G = Norm-Nr,
  Spalte I = Menge. Sortiert nach Abladestelle aufsteigend, Leerzeile
  zwischen Abladestellen-Gruppen.
- Menge wird auf das naechste volle Vielfache der Fuellmenge aufgerundet
  (ganze KLT/Packeinheiten), angepasste Menge in roter Schrift.
- Packeinheiten < 5 je Artikel -> komplette Zeile zu "DHL UPS" (gruen
  ausgefuellt), da zu wenig fuer eine eigene Palette.
- Rest-Packeinheiten (nach vollen Paletten) werden je Abladestelle
  versucht mit anderen Artikeln zu einer Mix-Palette zusammenzulegen
  (bis zur Lagen-Kapazitaet lt. Stammdaten: 10 bei Standard-Paletten,
  20 bei VWPAL), damit keine Palette mit nur bis zu 5 Stueck alleine
  dasteht. Nicht unterzubringende Reste -> ebenfalls "DHL UPS".
- Abholdatum (Planungsdatum) wird einmalig in Zelle M2 eingetragen.

WICHTIG (erster Testaufbau): die Mix-Paletten-Logik ist eine Heuristik
(groesste Reste zuerst kombinieren) - bei echten Tagesdaten bitte pruefen,
ob die Zusammenlegung so zustande kommt wie gewuenscht, und Rueckmeldung
geben, falls nicht.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import openpyxl
import pandas as pd
import streamlit as st
from openpyxl.styles import Font, PatternFill

VORLAGE_DATEI = Path(__file__).resolve().parent / "dispo_dashboard" / "planung_vorlage.xlsx"

ERSTE_DATENZEILE = 5
ROT = "FFFF0000"
GRUEN_FUELLUNG = PatternFill(patternType="solid", fgColor="FF92D050")
MINDEST_PACKEINHEITEN_FUER_PALETTE = 5  # darunter: einzeln nicht paletten-/versandfaehig -> DHL/UPS


# --- Referenzdaten aus der Vorlage (Füllmenge, Palettentyp) -----------------

def _lade_fuellmenge_je_artikel() -> dict:
    """Füllmenge je Norm-Nr (Blatt "Almanca Hilfsdaten", Spalte C/D - genau
    die Quelle, die auch die Live-Formeln in der Vorlage fuer Spalte J
    (Füllmenge) nutzen)."""
    try:
        hilfsdaten = pd.read_excel(VORLAGE_DATEI, sheet_name="Almanca Hilfsdaten")
    except (FileNotFoundError, ValueError):
        return {}
    spalten = hilfsdaten.columns
    if len(spalten) < 4:
        return {}
    norm_nr_spalte, fuellmenge_spalte = spalten[2], spalten[3]
    tabelle = hilfsdaten[[norm_nr_spalte, fuellmenge_spalte]].dropna()
    tabelle.columns = ["Norm-Nr", "Fuellmenge"]
    tabelle = tabelle.drop_duplicates(subset="Norm-Nr", keep="first")
    tabelle["Norm-Nr"] = pd.to_numeric(tabelle["Norm-Nr"], errors="coerce")
    tabelle = tabelle.dropna(subset=["Norm-Nr"])
    tabelle["Norm-Nr"] = tabelle["Norm-Nr"].astype(int)
    return dict(zip(tabelle["Norm-Nr"], tabelle["Fuellmenge"]))


def _lade_palettenspezifikation() -> dict:
    """(Lagerort, Norm-Nr) -> {anzahl_pro_lage, anzahl_volle_palette, typ}
    aus dem Blatt "Stammdaten" (dieselbe Quelle, die auch die Live-Formel
    fuer Spalte N "Paletten" nutzt). "Lagerort" hier = der Abladestellen-
    Code aus dem Kundenauftrag (siehe Modul-Docstring)."""
    try:
        stamm = pd.read_excel(VORLAGE_DATEI, sheet_name="Stammdaten")
    except (FileNotFoundError, ValueError):
        return {}
    noetige_spalten = ["Lagerort", "Norm NR.", "Anzahl Pro Lage", "Anzahl ", "Paletten"]
    if not set(noetige_spalten) <= set(stamm.columns):
        return {}
    tabelle = stamm[noetige_spalten].dropna(subset=["Lagerort", "Norm NR."]).copy()
    tabelle["Norm NR."] = pd.to_numeric(tabelle["Norm NR."], errors="coerce")
    tabelle = tabelle.dropna(subset=["Norm NR."])
    tabelle["Norm NR."] = tabelle["Norm NR."].astype(int)
    tabelle["Lagerort"] = tabelle["Lagerort"].astype(str).str.strip()
    tabelle = tabelle.drop_duplicates(subset=["Lagerort", "Norm NR."], keep="first")

    spezifikation = {}
    for lagerort, norm_nr, pro_lage, voll, typ in zip(
        tabelle["Lagerort"], tabelle["Norm NR."], tabelle["Anzahl Pro Lage"],
        tabelle["Anzahl "], tabelle["Paletten"],
    ):
        spezifikation[(lagerort, norm_nr)] = {
            "anzahl_pro_lage": pro_lage if pd.notna(pro_lage) and pro_lage > 0 else 10,
            "anzahl_volle_palette": voll if pd.notna(voll) and voll > 0 else 10,
            "typ": typ if pd.notna(typ) else "",
        }
    return spezifikation


_FUELLMENGE_JE_ARTIKEL = _lade_fuellmenge_je_artikel()
_PALETTENSPEZIFIKATION = _lade_palettenspezifikation()

# Standardwert, falls ein (Lagerort, Norm-Nr) nicht in Stammdaten vorkommt.
_STANDARD_PALETTE = {"anzahl_pro_lage": 10, "anzahl_volle_palette": 10, "typ": ""}


def _fuellmenge(norm_nr) -> float:
    return _FUELLMENGE_JE_ARTIKEL.get(norm_nr, 1.0) or 1.0


def _palettenspezifikation(lagerort: str, norm_nr) -> dict:
    return _PALETTENSPEZIFIKATION.get((lagerort, norm_nr), _STANDARD_PALETTE)


# --- Kundenauftraege -> Rueckstaende / Planbar -------------------------------

def _splitte_auftraege(positionen: pd.DataFrame, planungsdatum) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Kundenauftraege vom aeltesten Ladedatum bis zum Planungsdatum.
    Fehlmenge > 0 -> Rueckstand, sonst -> planbar (Bestand deckt die
    offene Menge lt. Dispo-Logik)."""
    fenster = positionen[positionen["Ladedatum"] <= pd.Timestamp(planungsdatum)].copy()
    fenster = fenster.sort_values("Ladedatum")
    rueckstand = fenster[fenster["Fehlmenge"] > 0]
    planbar = fenster[(fenster["Fehlmenge"] <= 0) & (fenster["Offene Menge"] > 0)]
    return rueckstand, planbar


def _gruppiere_je_abladestelle_artikel(df: pd.DataFrame) -> pd.DataFrame:
    """Mehrere Positionen derselben Abladestelle+Artikel im Zeitfenster zu
    einer Zeile zusammenfassen (fuer EINEN Kommissionier-/Palettenlauf)."""
    gruppiert = (
        df.groupby(["Abladestelle", "Norm-Nr"], as_index=False)
        .agg(Menge=("Offene Menge", "sum"), Ladedatum=("Ladedatum", "min"))
    )
    return gruppiert.sort_values(["Abladestelle", "Norm-Nr"]).reset_index(drop=True)


# --- Mengen aufrunden auf volle Füllmenge-Einheiten -------------------------

def _runde_auf_fuellmenge(gruppiert: pd.DataFrame) -> pd.DataFrame:
    df = gruppiert.copy()
    df["Fuellmenge"] = df["Norm-Nr"].apply(_fuellmenge)
    df["Packeinheiten"] = (df["Menge"] / df["Fuellmenge"]).apply(math.ceil)
    df["Menge urspruenglich"] = df["Menge"]
    df["Menge"] = df["Packeinheiten"] * df["Fuellmenge"]
    df["Menge_gerundet"] = df["Menge"] != df["Menge urspruenglich"]
    return df


# --- Mix-Paletten je Abladestelle: Reste nach vollen Paletten kombinieren ---

def _teile_in_paletten_und_rest(zeile, lagerort: str) -> tuple[int, int, dict]:
    spezifikation = _palettenspezifikation(lagerort, zeile["Norm-Nr"])
    kapazitaet = int(spezifikation["anzahl_volle_palette"])
    packeinheiten = int(zeile["Packeinheiten"])
    volle_paletten = packeinheiten // kapazitaet if kapazitaet else 0
    rest = packeinheiten - volle_paletten * kapazitaet
    return volle_paletten, rest, spezifikation


def _plane_abladestelle(gruppe: pd.DataFrame, lagerort: str) -> tuple[list[dict], list[dict]]:
    """Gibt (planungszeilen, dhl_ups_zeilen) fuer eine Abladestelle zurueck.
    planungszeilen: Artikel mit ausreichend Packeinheiten fuer mind. eine
    volle Palette (Reste werden, wenn kombinierbar, einem Artikel der
    Gruppe als Mix-Palette zugeschlagen - sonst zu DHL/UPS)."""
    planungszeilen: list[dict] = []
    offene_reste: list[dict] = []  # Kandidaten fuer Mix-Palette

    for _, zeile in gruppe.iterrows():
        packeinheiten = int(zeile["Packeinheiten"])
        if packeinheiten < MINDEST_PACKEINHEITEN_FUER_PALETTE:
            offene_reste.append({
                "Norm-Nr": zeile["Norm-Nr"], "Menge": zeile["Menge"],
                "Packeinheiten": packeinheiten, "Menge_gerundet": zeile["Menge_gerundet"],
                "angehaengt": False,
            })
            continue

        volle_paletten, rest, spezifikation = _teile_in_paletten_und_rest(zeile, lagerort)
        if volle_paletten > 0:
            kapazitaet = int(spezifikation["anzahl_volle_palette"])
            planungszeilen.append({
                "Norm-Nr": zeile["Norm-Nr"],
                "Menge": volle_paletten * kapazitaet * zeile["Fuellmenge"],
                "Menge_gerundet": zeile["Menge_gerundet"],
                "anzahl_pro_lage": spezifikation["anzahl_pro_lage"],
            })
        if rest > 0:
            # VWPAL: ein Rest von genau der Haelfte der Lagen-Kapazitaet
            # (z. B. 10 von 20) soll nicht alleine stehen - bevorzugt
            # auffuellen, daher mit hoeherer Prioritaet (groesster Rest
            # zuerst) in die Kombinationsliste.
            offene_reste.append({
                "Norm-Nr": zeile["Norm-Nr"], "Menge": rest * zeile["Fuellmenge"],
                "Packeinheiten": rest, "Menge_gerundet": True,
                "anzahl_pro_lage": spezifikation["anzahl_pro_lage"],
                "angehaengt": False,
            })

    # Reste absteigend nach Packeinheiten kombinieren (groesster Rest bildet
    # den Grundstock einer Mix-Palette, kleinere Reste werden - soweit die
    # Lagen-Kapazitaet reicht - dazugelegt).
    offene_reste.sort(key=lambda r: r["Packeinheiten"], reverse=True)
    dhl_ups_zeilen: list[dict] = []
    while offene_reste:
        grundstock = offene_reste.pop(0)
        kapazitaet = grundstock.get("anzahl_pro_lage", 10)
        summe = grundstock["Packeinheiten"]
        mix_artikel = [grundstock]
        rest_liste = []
        for kandidat in offene_reste:
            if summe + kandidat["Packeinheiten"] <= kapazitaet:
                summe += kandidat["Packeinheiten"]
                mix_artikel.append(kandidat)
            else:
                rest_liste.append(kandidat)
        offene_reste = rest_liste

        if summe < MINDEST_PACKEINHEITEN_FUER_PALETTE or len(mix_artikel) == 1 and summe < MINDEST_PACKEINHEITEN_FUER_PALETTE:
            for artikel in mix_artikel:
                dhl_ups_zeilen.append(artikel)
        else:
            for artikel in mix_artikel:
                planungszeilen.append({
                    "Norm-Nr": artikel["Norm-Nr"], "Menge": artikel["Menge"],
                    "Menge_gerundet": artikel["Menge_gerundet"],
                    "anzahl_pro_lage": kapazitaet,
                })

    return planungszeilen, dhl_ups_zeilen


def _baue_planung_und_versand(planbar: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Komplette Planbar-Menge -> (Almanca-Zeilen, DHL/UPS-Zeilen), je
    Abladestelle gruppiert und sortiert, mit Mix-Paletten-Logik."""
    if planbar.empty:
        return [], []
    gruppiert = _gruppiere_je_abladestelle_artikel(planbar)
    gerundet = _runde_auf_fuellmenge(gruppiert)

    alle_planungszeilen: list[dict] = []
    alle_dhl_ups_zeilen: list[dict] = []
    for abladestelle, gruppe in gerundet.groupby("Abladestelle", sort=True):
        planungszeilen, dhl_ups_zeilen = _plane_abladestelle(gruppe, abladestelle)
        for zeile in planungszeilen:
            zeile["Abladestelle"] = abladestelle
            alle_planungszeilen.append(zeile)
        for zeile in dhl_ups_zeilen:
            zeile["Abladestelle"] = abladestelle
            alle_dhl_ups_zeilen.append(zeile)
    return alle_planungszeilen, alle_dhl_ups_zeilen


# --- In die Vorlage schreiben -------------------------------------------

def _schreibe_zeilen(ws, zeilen: list[dict], *, rot_wenn_gerundet: bool, gruen_fuellung: bool) -> None:
    aktuelle_abladestelle = None
    zeile_nr = ERSTE_DATENZEILE
    for eintrag in zeilen:
        if aktuelle_abladestelle is not None and eintrag["Abladestelle"] != aktuelle_abladestelle:
            zeile_nr += 1  # Leerzeile zwischen Abladestellen-Gruppen
        aktuelle_abladestelle = eintrag["Abladestelle"]

        ws.cell(row=zeile_nr, column=3, value=eintrag["Abladestelle"])  # C: Lagerort
        ws.cell(row=zeile_nr, column=7, value=int(eintrag["Norm-Nr"]))  # G: Norm-Nr
        menge_zelle = ws.cell(row=zeile_nr, column=9, value=eintrag["Menge"])  # I: Menge

        if rot_wenn_gerundet and eintrag.get("Menge_gerundet"):
            bisheriger_font = menge_zelle.font
            menge_zelle.font = Font(
                name=bisheriger_font.name, size=bisheriger_font.size,
                bold=bisheriger_font.bold, color=ROT,
            )
        if gruen_fuellung:
            for spalte in (3, 7, 9):
                ws.cell(row=zeile_nr, column=spalte).fill = GRUEN_FUELLUNG

        zeile_nr += 1


def _schreibe_rueckstaende(ws, rueckstand: pd.DataFrame) -> None:
    gruppiert = _gruppiere_je_abladestelle_artikel(rueckstand)
    zeile_nr = ERSTE_DATENZEILE
    aktuelle_abladestelle = None
    rote_schrift = Font(size=15, color=ROT)
    for _, eintrag in gruppiert.iterrows():
        if aktuelle_abladestelle is not None and eintrag["Abladestelle"] != aktuelle_abladestelle:
            zeile_nr += 1
        aktuelle_abladestelle = eintrag["Abladestelle"]

        ws.cell(row=zeile_nr, column=3, value=eintrag["Abladestelle"]).font = rote_schrift
        ws.cell(row=zeile_nr, column=7, value=int(eintrag["Norm-Nr"])).font = rote_schrift
        ws.cell(row=zeile_nr, column=9, value=eintrag["Menge"]).font = rote_schrift
        # Ladedatum (fuer Lageraufträge) in die Spalte "Lagerauftrag" (L).
        ws.cell(row=zeile_nr, column=12, value=eintrag["Ladedatum"].strftime("%d.%m.%Y")).font = rote_schrift
        zeile_nr += 1


def _palettenspezifikation_abdeckung(planbar: pd.DataFrame) -> tuple[int, int]:
    """(gefunden, gesamt) (Abladestelle, Norm-Nr)-Kombinationen mit echter
    Palettenspezifikation in Stammdaten vs. Standard-Fallback (10/10)."""
    if planbar.empty:
        return 0, 0
    kombinationen = planbar[["Abladestelle", "Norm-Nr"]].drop_duplicates()
    gefunden = sum(
        1 for _, r in kombinationen.iterrows()
        if (r["Abladestelle"], r["Norm-Nr"]) in _PALETTENSPEZIFIKATION
    )
    return gefunden, len(kombinationen)


def erstelle_planungsdatei(positionen: pd.DataFrame, planungsdatum) -> tuple[bytes, dict]:
    rueckstand, planbar = _splitte_auftraege(positionen, planungsdatum)
    planungszeilen, dhl_ups_zeilen = _baue_planung_und_versand(planbar)
    palette_gefunden, palette_gesamt = _palettenspezifikation_abdeckung(planbar)

    wb = openpyxl.load_workbook(VORLAGE_DATEI)
    _schreibe_zeilen(wb["Almanca"], planungszeilen, rot_wenn_gerundet=True, gruen_fuellung=False)
    _schreibe_zeilen(wb["DHL UPS"], dhl_ups_zeilen, rot_wenn_gerundet=False, gruen_fuellung=True)
    _schreibe_rueckstaende(wb["Rückstände"], rueckstand)
    wb["Almanca"]["M2"] = pd.Timestamp(planungsdatum).strftime("%d.%m. VW")

    puffer = io.BytesIO()
    wb.save(puffer)
    puffer.seek(0)

    kennzahlen = {
        "rueckstand_artikel": rueckstand["Norm-Nr"].nunique(),
        "planung_zeilen": len(planungszeilen),
        "dhl_ups_zeilen": len(dhl_ups_zeilen),
        "palette_spezifikation_gefunden": palette_gefunden,
        "palette_spezifikation_gesamt": palette_gesamt,
    }
    return puffer.getvalue(), kennzahlen


# --- Streamlit-Oberflaeche ---------------------------------------------------

def render_planung_tab() -> None:
    st.title("Planung Erstellung")
    st.markdown(
        '<span class="vwai-badge">✨ Kommissionier-/Palettenplanung</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Erster Testaufbau. Nutzt dieselben Daten wie Dashboard Dispo "
        "(Bedarf + Bestand) - dort bitte zuerst die SAP-Exporte hochladen. "
        "Die Mix-Paletten-Zusammenlegung ist eine Heuristik (groesste Reste "
        "zuerst kombinieren) - bitte mit echten Tagesdaten pruefen."
    )

    daten = st.session_state.get("dispo_daten")
    if not daten:
        st.info("Bitte zuerst im Dashboard Dispo SAP-Exporte hochladen.")
        return

    planungsdatum = st.date_input(
        "Planungsdatum (Kundenauftraege vom aeltesten Ladedatum bis hierhin)",
        value=daten["stichtag"],
        key="planung_datum",
    )

    if st.button("📋 Planung erstellen", key="planung_erstellen"):
        with st.spinner("Planung wird erstellt..."):
            inhalt, kennzahlen = erstelle_planungsdatei(daten["positionen"], planungsdatum)
        st.session_state["planung_datei"] = inhalt
        st.session_state["planung_kennzahlen"] = kennzahlen
        st.session_state["planung_erstellt_fuer"] = planungsdatum

    kennzahlen = st.session_state.get("planung_kennzahlen")
    if not kennzahlen or st.session_state.get("planung_erstellt_fuer") != planungsdatum:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artikel im Rückstand", kennzahlen["rueckstand_artikel"])
    c2.metric("Planungszeilen (Almanca)", kennzahlen["planung_zeilen"])
    palette_gefunden = kennzahlen["palette_spezifikation_gefunden"]
    palette_gesamt = kennzahlen["palette_spezifikation_gesamt"]
    c4.metric(
        "Palettentyp bekannt (Stammdaten)",
        f"{palette_gefunden} von {palette_gesamt}" if palette_gesamt else "–",
    )
    if palette_gesamt and palette_gefunden < palette_gesamt:
        st.caption(
            f"⚠️ Für {palette_gesamt - palette_gefunden} von {palette_gesamt} "
            "Abladestelle/Artikel-Kombinationen steht keine Palettenspezifikation "
            "in Stammdaten - dort wurde der Standard (10 Stück/Lage, 10 Stück/"
            "volle Palette) angenommen. Bei echten VWPAL-Kombinationen (20/Lage) "
            "kann die Mix-Paletten-Zusammenlegung dadurch zu frueh in DHL/UPS "
            "ausweichen, statt die hoehere Kapazitaet zu nutzen."
        )
    c3.metric("Zeilen DHL/UPS", kennzahlen["dhl_ups_zeilen"])

    st.download_button(
        "📥 Planungsdatei herunterladen",
        data=st.session_state["planung_datei"],
        file_name=f"Planung_{pd.Timestamp(planungsdatum):%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="planung_download",
    )
