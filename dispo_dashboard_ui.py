"""Oberflaeche fuer den Reiter "Dashboard Dispo" in VW AI.

Zeigt die von dispo_dashboard (config/loaders/logic - unveraendert genutzt)
berechnete Auswertung an. Die taeglichen SAP-Exporte koennen entweder direkt
hochgeladen werden (funktioniert ueberall, auch auf Streamlit Cloud) oder -
nur in der lokal installierten Version - aus einem Ordner (z. B. Netzlaufwerk)
gelesen werden.
"""

import io
import json
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dispo_dashboard import config, loaders, logic

ORDNER_DATEI = ".dispo_sap_ordner.txt"
KONTAKTE_DATEI = ".dispo_kontakte.json"
REICHWEITE_DATEI = ".dispo_reichweite.json"

QUELLEN = [
    ("bedarf", "Bedarf (Lieferplan-Einteilungen)"),
    ("bestand", "Bestand (EWM)"),
    ("zugang", "Zugänge (ZMM1000)"),
    ("stockreport", "Stock Report Versender (nur Info)"),
]

STATUS_REIHENFOLGE = [
    "Rückstand ungedeckt",
    "Rückstand, Zugang kommt",
    "Rückstand gedeckt",
    "Engpass",
    "Zugang zu spät",
    "Fehlmenge später",
    "Gedeckt",
    "Erledigt",
]

TRANSPORTARTEN = ["Luftfracht", "Minivan", "Express LKW", "LKW"]

POSITIONEN_SPALTEN = [
    "Werk", "Kunde", "Abladestelle", "Norm-Nr", "Kurztext", "Ladedatum",
    "Wunschtermin", "Bestellmenge", "Geliefert", "Offene Menge", "Fehlmenge",
    "Gedeckt ab", "Verspätung (Tage)", "Deckender Import", "Versandart", "Status",
]

ARTIKEL_SPALTEN = [
    "Norm-Nr", "Kurztext", "Kunden", "Bestand verfügbar", "Offene Menge gesamt",
    "Rückstand (Menge)", "Erste Fehlmenge am", "Zugänge unterwegs",
    "Nächster Zugang", "Reichweite (Tage)", "Ampel",
]

MENGEN_SPALTEN_POSITIONEN = ["Bestellmenge", "Geliefert", "Offene Menge", "Fehlmenge"]
TAGE_SPALTEN_POSITIONEN = ["Verspätung (Tage)"]
DATUM_SPALTEN_POSITIONEN = ["Ladedatum", "Wunschtermin", "Gedeckt ab"]

MENGEN_SPALTEN_ARTIKEL = [
    "Bestand verfügbar", "Offene Menge gesamt", "Rückstand (Menge)", "Zugänge unterwegs",
]
TAGE_SPALTEN_ARTIKEL = ["Reichweite (Tage)"]
DATUM_SPALTEN_ARTIKEL = ["Erste Fehlmenge am", "Nächster Zugang"]

_AMPEL_FARBEN = {"Rot": "#ef4444", "Gelb": "#f59e0b", "Grün": "#22c55e"}
_STATUS_FARBEN = {
    "Rückstand ungedeckt": "#ef4444",
    "Engpass": "#ef4444",
    "Rückstand, Zugang kommt": "#f59e0b",
    "Zugang zu spät": "#f59e0b",
    "Rückstand gedeckt": "#f59e0b",
    "Gedeckt": "#22c55e",
    "Erledigt": "#22c55e",
}
_VERSANDART_FARBEN = {"Gebietsspediteur": "#22c55e", "Sonderfahrt": "#ef4444"}
_TRANSPORTART_FARBEN = {
    "Luftfracht": "#ef4444",
    "Minivan": "#f59e0b",
    "Express LKW": "#f59e0b",
    "LKW": "#22c55e",
}

# --- Uebersetzung fuer die Ausgabedatei --------------------------------------
UEBERSETZUNG_TR = {
    "Werk": "Tesis", "Kunde": "Müşteri", "Abladestelle": "Boşaltma Yeri",
    "Norm-Nr": "Parça No", "Kurztext": "Kısa Metin", "Ladedatum": "Yükleme Tarihi",
    "Wunschtermin": "İstenen Tarih", "Bestellmenge": "Sipariş Miktarı",
    "Geliefert": "Teslim Edilen", "Offene Menge": "Açık Miktar",
    "Fehlmenge": "Eksik Miktar", "Gedeckt ab": "Karşılanma Tarihi",
    "Verspätung (Tage)": "Gecikme (Gün)", "Deckender Import": "Karşılayan İthalat",
    "Versandart": "Sevkiyat Türü", "Status": "Durum",
}
STATUS_TR = {
    "Rückstand ungedeckt": "Karşılanmamış Gecikme",
    "Rückstand, Zugang kommt": "Gecikme, Sevkiyat Geliyor",
    "Rückstand gedeckt": "Gecikme Karşılandı",
    "Engpass": "Darboğaz",
    "Zugang zu spät": "Sevkiyat Geç Kalıyor",
    "Fehlmenge später": "Eksik Miktar İleride",
    "Gedeckt": "Karşılandı",
    "Erledigt": "Tamamlandı",
}
VERSANDART_TR = {"Gebietsspediteur": "Bölge Nakliyecisi", "Sonderfahrt": "Özel Sefer"}


def lade_gespeicherten_ordner() -> str:
    try:
        return Path(ORDNER_DATEI).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def speichere_ordner(pfad: str) -> None:
    Path(ORDNER_DATEI).write_text(pfad, encoding="utf-8")


def lade_kontakte() -> dict:
    try:
        return json.loads(Path(KONTAKTE_DATEI).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def speichere_kontakte(kontakte: dict) -> None:
    Path(KONTAKTE_DATEI).write_text(
        json.dumps(kontakte, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def lade_reichweite_notizen() -> dict:
    try:
        return json.loads(Path(REICHWEITE_DATEI).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def speichere_reichweite_notizen(daten: dict) -> None:
    Path(REICHWEITE_DATEI).write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Zusaetzliche, von logic.py unabhaengige Ableitungen ---------------------
# (logic.py/loaders.py bleiben unveraendert; diese Funktionen werten nur deren
# bereits berechnete Spalten weiter aus.)

def _versandart(zeile) -> str:
    """Gebietsspediteur, wenn der deckende Zugang vor dem Ladetermin da ist,
    sonst Sonderfahrt. Nur relevant, wenn ueberhaupt eine Fehlmenge besteht."""
    if zeile["Fehlmenge"] <= 0 or pd.isna(zeile["Gedeckt ab"]):
        return ""
    if zeile["Gedeckt ab"] <= zeile["Ladedatum"]:
        return "Gebietsspediteur"
    return "Sonderfahrt"


def _transportart(tage_bis_ladedatum) -> str:
    """Abbauplan-Transportart nach Tagen bis Ladedatum (auch negativ = ueberfaellig)."""
    if pd.isna(tage_bis_ladedatum):
        return ""
    if tage_bis_ladedatum <= 2:
        return "Luftfracht"
    if tage_bis_ladedatum <= 5:
        return "Minivan"
    if tage_bis_ladedatum <= 8:
        return "Express LKW"
    return "LKW"


def _deckende_importe(positionen: pd.DataFrame, zugang_vorbereitet: pd.DataFrame) -> pd.Series:
    """Referenznummer(n) der Zugaenge, die am 'Gedeckt ab'-Datum fuer den Artikel ankommen."""
    if zugang_vorbereitet.empty:
        return pd.Series([""] * len(positionen), index=positionen.index)
    referenzen = (
        zugang_vorbereitet.groupby(["Norm-Nr", "Ankunft gerechnet"])["Referenz"]
        .apply(lambda s: ", ".join(sorted({r for r in s if r})))
    )

    def _lookup(zeile):
        if pd.isna(zeile["Gedeckt ab"]):
            return ""
        return referenzen.get((zeile["Norm-Nr"], zeile["Gedeckt ab"]), "")

    return positionen.apply(_lookup, axis=1)


def _lade_und_berechne(ordner: str) -> dict:
    dateien = loaders.neueste_dateien(ordner)
    fehlend = [t for t in ["bedarf", "bestand", "zugang"] if t not in dateien]
    if fehlend:
        raise ValueError(f"Es fehlen Dateien fuer: {', '.join(fehlend)}")

    stichtag = loaders.datum_der_datei(dateien["bedarf"][0])
    bedarf = loaders.lade_bedarf(dateien["bedarf"][0])
    _, bestand_artikel = loaders.lade_bestand(dateien["bestand"][0])
    zugang = loaders.lade_zugang(dateien["zugang"][0])
    positionen, artikel, zugang_vorbereitet = logic.berechne(bedarf, bestand_artikel, zugang, stichtag)

    positionen = positionen.copy()
    positionen["Deckender Import"] = _deckende_importe(positionen, zugang_vorbereitet)
    positionen["Versandart"] = positionen.apply(_versandart, axis=1)
    positionen["Transportart"] = positionen["Tage bis Ladedatum"].apply(_transportart)

    datenstand = [
        (label, loaders.datum_der_datei(dateien[t][0], stichtag), Path(dateien[t][0]).name)
        for t, label in QUELLEN if t in dateien
    ]
    return {
        "stichtag": stichtag,
        "positionen": positionen,
        "artikel": artikel,
        "datenstand": datenstand,
    }


def _filter_auswahl(df: pd.DataFrame, spalte: str, label: str, bereich: str) -> pd.DataFrame:
    optionen = sorted({str(x) for x in df[spalte].dropna() if str(x) != ""})
    auswahl = st.multiselect(label, optionen, key=f"dispo_filter_{bereich}_{spalte}")
    if not auswahl:
        return df
    return df[df[spalte].astype(str).isin(auswahl)]


def _faerbe(farben: dict):
    def _stil(wert):
        farbe = farben.get(wert)
        return f"background-color: {farbe}; color: #0a0a0f; font-weight: 600;" if farbe else ""
    return _stil


def _faerbe_positiv(farbe: str):
    def _stil(wert):
        return f"background-color: {farbe}33;" if wert and wert > 0 else ""
    return _stil


# --- Zahlen-/Datumsformat: Tausenderpunkt, keine Nachkommastellen -----------

def _fmt_menge(wert) -> str:
    if pd.isna(wert):
        return "–"
    return f"{wert:,.0f}".replace(",", ".")


def _fmt_tage(wert) -> str:
    if pd.isna(wert):
        return "–"
    return f"{wert:.0f}"


def _fmt_datum(wert) -> str:
    if pd.isna(wert):
        return "–"
    return pd.Timestamp(wert).strftime("%d.%m.%Y")


def _zeige_tabelle(
    df: pd.DataFrame,
    spalten: list,
    *,
    menge_spalten: tuple = (),
    tage_spalten: tuple = (),
    datum_spalten: tuple = (),
    farben: dict | None = None,
) -> None:
    # Werte VOR der Anzeige in fertige Text-Strings umwandeln (statt
    # Styler.format): st.dataframe zeigt leere/NaN-Zellen sonst immer als
    # woertliches "None" an, unabhaengig von Styler- oder column_config-
    # Formatierung - das ist ein Streamlit-eigenes Verhalten.
    anzeige = df[spalten].copy()
    for s in menge_spalten:
        anzeige[s] = anzeige[s].apply(_fmt_menge)
    for s in tage_spalten:
        anzeige[s] = anzeige[s].apply(_fmt_tage)
    for s in datum_spalten:
        anzeige[s] = anzeige[s].apply(_fmt_datum)
    styler = anzeige.style
    for spalte, farbkarte in (farben or {}).items():
        styler = styler.map(_faerbe(farbkarte), subset=[spalte])
    st.dataframe(styler, hide_index=True, use_container_width=True)


# --- Legende + Uebersicht/Eskalation -----------------------------------------

def _render_legende() -> None:
    with st.expander("Legende"):
        st.markdown(
            "- **Ampel je Artikel:** 🔴 Rot = erste Fehlmenge ≤14 Tage, "
            "🟡 Gelb ≤30 Tage, 🟢 Grün sonst\n"
            "- **Status:** 🔴 Rückstand ungedeckt/Engpass · 🟡 Rückstand mit "
            "Zugang/Zugang zu spät/Rückstand gedeckt · 🟢 Gedeckt/Erledigt\n"
            "- **Versandart:** Gebietsspediteur = Ware kommt rechtzeitig vor "
            "dem Ladetermin an · Sonderfahrt = Ware kommt erst danach an\n"
            "- **Abbauplan-Transportart** (nach Tagen bis Ladedatum): "
            "🔴 Luftfracht ≤2 Tage · 🟡 Minivan 3–5 Tage · 🟡 Express LKW 6–8 Tage "
            "· 🟢 LKW ab 9 Tage\n"
            "- **Eskalation** (Deckungsgrad Rückstand durch Transporte): "
            "🟢 ≥80 % · 🟡 50–79 % · 🔴 <50 %"
        )


def _render_uebersicht(artikel: pd.DataFrame) -> None:
    gesamt = len(artikel)
    im_rueckstand = artikel[artikel["Rückstand (Menge)"] > 0]
    anzahl_rueckstand = len(im_rueckstand)
    mit_transport = int((im_rueckstand["Zugänge unterwegs"] > 0).sum())
    ohne_transport = anzahl_rueckstand - mit_transport

    rueckstand_summe = im_rueckstand["Rückstand (Menge)"].sum()
    gedeckt_summe = im_rueckstand[["Rückstand (Menge)", "Zugänge unterwegs"]].min(axis=1).sum()
    deckungsgrad = (gedeckt_summe / rueckstand_summe * 100) if rueckstand_summe else 100.0

    if deckungsgrad >= 80:
        text, farbe = "Rückstand ist gut durch Transporte gedeckt.", "#22c55e"
    elif deckungsgrad >= 50:
        text, farbe = "Deckung reicht nur teilweise - bitte pruefen.", "#f59e0b"
    else:
        text, farbe = "Deckung reicht bei weitem nicht - Abbauplan funktioniert so nicht.", "#ef4444"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artikel im Rückstand", f"{anzahl_rueckstand} von {gesamt}")
    c2.metric("davon auf Transport", mit_transport)
    c3.metric("davon ohne eingeplante Menge", ohne_transport)
    c4.metric("Deckungsgrad Rückstand", _fmt_tage(deckungsgrad) + " %")

    st.markdown(
        f"<div style='padding:10px 14px;border-radius:8px;background:{farbe}22;"
        f"border:1px solid {farbe};color:{farbe};font-weight:600;'>"
        f"Eskalation: {text}</div>",
        unsafe_allow_html=True,
    )


# --- Abbauplan ----------------------------------------------------------------

def _abbauplan(positionen: pd.DataFrame) -> pd.DataFrame:
    offen = positionen[positionen["Fehlmenge"] > 0]
    pivot = offen.pivot_table(
        index=["Norm-Nr", "Kurztext"],
        columns="Transportart",
        values="Fehlmenge",
        aggfunc="sum",
        fill_value=0.0,
    )
    for spalte in TRANSPORTARTEN:
        if spalte not in pivot.columns:
            pivot[spalte] = 0.0
    pivot = pivot[TRANSPORTARTEN]
    pivot["Gesamt offen"] = pivot.sum(axis=1)
    return pivot.reset_index().sort_values("Gesamt offen", ascending=False)


def _render_abbauplan(positionen: pd.DataFrame) -> None:
    st.subheader("Abbauplan")
    st.caption(
        "Je Artikel, welche offene Menge mit welcher Transportart noch "
        "aufgeholt werden kann (nach Tagen bis Ladedatum: ≤2 Luftfracht, "
        "3–5 Minivan, 6–8 Express LKW, ab 9 LKW)."
    )
    plan = _abbauplan(positionen)
    if plan.empty:
        st.success("Kein offener Rückstand - kein Abbauplan noetig.")
        return

    formate = {s: _fmt_menge for s in TRANSPORTARTEN + ["Gesamt offen"]}
    styler = plan.style.format(formate)
    for spalte in TRANSPORTARTEN:
        styler = styler.map(_faerbe_positiv(_TRANSPORTART_FARBEN[spalte]), subset=[spalte])
    st.dataframe(styler, hide_index=True, use_container_width=True)


# --- Reichweite beim Kunden (dynamisch) ---------------------------------------

def _verbrauch_pro_woche(positionen: pd.DataFrame) -> pd.DataFrame:
    rueckstand_positionen = positionen[positionen["Status"].str.startswith("Rückstand")]
    if rueckstand_positionen.empty:
        return rueckstand_positionen[["Kunde", "Norm-Nr", "Kurztext"]].assign(**{"Verbrauch (Stk/Woche)": []})

    spanne_tage = max((positionen["Ladedatum"].max() - positionen["Ladedatum"].min()).days, 1)
    wochen = max(spanne_tage / 7, 1)
    gruppe = (
        positionen.groupby(["Kunde", "Norm-Nr", "Kurztext"])["Bestellmenge"]
        .sum()
        .reset_index()
    )
    gruppe["Verbrauch (Stk/Woche)"] = gruppe["Bestellmenge"] / wochen

    relevante_kombis = set(zip(rueckstand_positionen["Kunde"], rueckstand_positionen["Norm-Nr"]))
    gruppe = gruppe[gruppe.apply(lambda z: (z["Kunde"], z["Norm-Nr"]) in relevante_kombis, axis=1)]
    return gruppe.drop(columns="Bestellmenge")


def _render_reichweite_tabelle(positionen: pd.DataFrame) -> None:
    st.subheader("Reichweite beim Kunden")
    st.caption(
        "Verbrauch wird aus den eingespielten Bestellungen berechnet (nur "
        "Artikel/Kunden aktuell im Rückstand). Bestand beim Kunden und Notiz "
        "bitte selbst eintragen - die Reichweite wird automatisch daraus "
        "berechnet und gespeichert."
    )
    basis = _verbrauch_pro_woche(positionen)
    if basis.empty:
        st.success("Kein offener Rückstand - keine Reichweiten-Pflege noetig.")
        return

    notizen = st.session_state.setdefault("dispo_reichweite", lade_reichweite_notizen())

    zeilen = []
    for _, zeile in basis.iterrows():
        schluessel = f"{zeile['Kunde']}|{zeile['Norm-Nr']}"
        gespeichert = notizen.get(schluessel, {})
        zeilen.append({
            "Kunde": zeile["Kunde"],
            "Norm-Nr": zeile["Norm-Nr"],
            "Kurztext": zeile["Kurztext"],
            "Verbrauch (Stk/Woche)": round(zeile["Verbrauch (Stk/Woche)"], 1),
            "Bestand beim Kunden": float(gespeichert.get("bestand", 0.0)),
            "Notiz": gespeichert.get("notiz", ""),
        })
    anzeige = pd.DataFrame(zeilen)
    anzeige["Reichweite (Wochen)"] = anzeige.apply(
        lambda z: round(z["Bestand beim Kunden"] / z["Verbrauch (Stk/Woche)"], 1)
        if z["Verbrauch (Stk/Woche)"] > 0 and z["Bestand beim Kunden"] > 0 else None,
        axis=1,
    )

    bearbeitet = st.data_editor(
        anzeige,
        hide_index=True,
        use_container_width=True,
        key="dispo_reichweite_editor",
        disabled=["Kunde", "Norm-Nr", "Kurztext", "Verbrauch (Stk/Woche)", "Reichweite (Wochen)"],
    )

    if st.button("Reichweite-Angaben speichern", key="dispo_reichweite_speichern"):
        neue_notizen = dict(notizen)
        for _, zeile in bearbeitet.iterrows():
            schluessel = f"{zeile['Kunde']}|{zeile['Norm-Nr']}"
            bestand = zeile["Bestand beim Kunden"]
            neue_notizen[schluessel] = {
                "bestand": float(bestand) if pd.notna(bestand) else 0.0,
                "notiz": zeile["Notiz"] or "",
            }
        speichere_reichweite_notizen(neue_notizen)
        st.session_state["dispo_reichweite"] = neue_notizen
        st.success("Gespeichert.")


# --- Ausgabedatei (Deutsch/Tuerkisch) -----------------------------------------

def _export_uebersetzen(df: pd.DataFrame, sprache: str) -> pd.DataFrame:
    export = df.copy()
    if "Status" in export.columns:
        export["Status"] = export["Status"].map(STATUS_TR) if sprache == "Türkçe" else export["Status"]
    if "Versandart" in export.columns:
        export["Versandart"] = (
            export["Versandart"].map(VERSANDART_TR).fillna("") if sprache == "Türkçe" else export["Versandart"]
        )
    if sprache == "Türkçe":
        export = export.rename(columns=UEBERSETZUNG_TR)
    return export


def _render_export(positionen: pd.DataFrame) -> None:
    st.subheader("Ausgabedatei")
    sprache = st.radio(
        "Sprache", ["Deutsch", "Türkçe"], horizontal=True, key="dispo_export_sprache"
    )

    export_df = positionen[POSITIONEN_SPALTEN].copy()
    for spalte in DATUM_SPALTEN_POSITIONEN:
        export_df[spalte] = export_df[spalte].apply(_fmt_datum)
    export_df = _export_uebersetzen(export_df, sprache)

    puffer = io.BytesIO()
    export_df.to_excel(puffer, index=False)
    puffer.seek(0)
    sprachkuerzel = "DE" if sprache == "Deutsch" else "TR"
    st.download_button(
        "📥 Ausgabedatei herunterladen",
        data=puffer,
        file_name=f"Dispo_Rueckstand_{sprachkuerzel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dispo_export_download",
    )


def render_dispo_tab() -> None:
    st.title("Dashboard Dispo")
    st.markdown(
        '<span class="vwai-badge">✨ Dispositions-Übersicht</span>',
        unsafe_allow_html=True,
    )

    _render_legende()

    hochgeladen = st.file_uploader(
        "SAP-Exporte hochladen (Bedarf, Bestand, Zugänge, optional Stock Report)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="dispo_upload",
    )

    with st.expander("Oder: Ordner mit SAP-Exporten (nur lokal verfuegbar, z. B. Netzlaufwerk)"):
        ordner = st.text_input(
            "Ordner mit den taeglichen SAP-Exporten",
            value=st.session_state.get("dispo_ordner", lade_gespeicherten_ordner()),
            key="dispo_ordner_input",
        )
        if st.button("Ordner merken", key="dispo_ordner_speichern"):
            speichere_ordner(ordner)
            st.session_state["dispo_ordner"] = ordner
            st.success("Ordner gemerkt - wird beim naechsten Start automatisch vorausgefuellt.")

    if hochgeladen:
        aktuelle_signatur = tuple(sorted((d.name, d.size) for d in hochgeladen))
        quelle_ordner = st.session_state.setdefault(
            "dispo_upload_ordner", tempfile.mkdtemp(prefix="dispo_upload_")
        )
    elif ordner:
        aktuelle_signatur = ordner
        quelle_ordner = ordner
    else:
        aktuelle_signatur = None
        quelle_ordner = None

    if not quelle_ordner:
        st.info("Bitte SAP-Exporte hochladen oder (nur lokal) einen Ordner angeben.")
        return

    kopf_links, kopf_rechts = st.columns([5, 1])
    with kopf_rechts:
        aktualisieren = st.button("🔄 Aktualisieren", key="dispo_aktualisieren")

    signatur_geaendert = st.session_state.get("dispo_geladene_signatur") != aktuelle_signatur
    if "dispo_daten" not in st.session_state or signatur_geaendert or aktualisieren:
        if hochgeladen:
            for datei in hochgeladen:
                (Path(quelle_ordner) / datei.name).write_bytes(datei.getvalue())
        with st.spinner("SAP-Exporte werden eingelesen..."):
            try:
                st.session_state["dispo_daten"] = _lade_und_berechne(quelle_ordner)
                st.session_state["dispo_geladene_signatur"] = aktuelle_signatur
            except (ValueError, FileNotFoundError) as exc:
                st.error(f"Fehler beim Einlesen: {exc}")
                return

    daten = st.session_state["dispo_daten"]
    stichtag = daten["stichtag"]
    positionen = daten["positionen"]
    artikel = daten["artikel"]

    with kopf_links:
        st.caption(f"Stichtag: {stichtag:%d.%m.%Y}")

    _render_uebersicht(artikel)

    st.divider()

    # --- Datenstand je Quelle -------------------------------------------------
    datenstand_zeilen = []
    for label, datum, name in daten["datenstand"]:
        veraltet = (stichtag - datum).days >= config.QUELLE_VERALTET_TAGE
        datenstand_zeilen.append({
            "Quelle": label,
            "Datenstand": datum.strftime("%d.%m.%Y") + (" ⚠️ veraltet" if veraltet else ""),
            "Datei": name,
        })
    st.dataframe(pd.DataFrame(datenstand_zeilen), hide_index=True, use_container_width=True)

    # --- Kennzahlen -------------------------------------------------------
    status_counts = positionen["Status"].value_counts()
    ampel_counts = artikel["Ampel"].value_counts()

    status_cols = st.columns(len(STATUS_REIHENFOLGE))
    for col, status in zip(status_cols, STATUS_REIHENFOLGE):
        col.metric(status, int(status_counts.get(status, 0)))

    ampel_cols = st.columns(3)
    for col, ampel in zip(ampel_cols, ["Rot", "Gelb", "Grün"]):
        col.metric(f"Ampel {ampel}", int(ampel_counts.get(ampel, 0)))

    st.divider()

    # --- Rückstand (nach Artikel sortiert, mit deckendem Import) --------------
    st.subheader("Rückstand")
    st.caption("Nach Ladedatum sortiert, mit der Referenznummer des deckenden Imports und der Versandart.")
    rueckstand = positionen[positionen["Status"].str.startswith("Rückstand")]
    f1, f2 = st.columns(2)
    with f1:
        rueckstand = _filter_auswahl(rueckstand, "Werk", "Werk", "rueckstand")
    with f2:
        rueckstand = _filter_auswahl(rueckstand, "Kunde", "Kunde", "rueckstand")
    _zeige_tabelle(
        rueckstand, POSITIONEN_SPALTEN,
        menge_spalten=MENGEN_SPALTEN_POSITIONEN,
        tage_spalten=TAGE_SPALTEN_POSITIONEN,
        datum_spalten=DATUM_SPALTEN_POSITIONEN,
        farben={"Status": _STATUS_FARBEN, "Versandart": _VERSANDART_FARBEN},
    )

    # --- Deckung je Artikel --------------------------------------------------
    st.subheader("Deckung je Artikel")
    st.caption("Zeile anklicken (Kaestchen links), um Reichweite-Grafik und Kontakt-E-Mail zu sehen.")
    deckung = _filter_auswahl(artikel, "Ampel", "Ampel", "deckung")
    anzeige_deckung = deckung[ARTIKEL_SPALTEN].copy()
    for s in MENGEN_SPALTEN_ARTIKEL:
        anzeige_deckung[s] = anzeige_deckung[s].apply(_fmt_menge)
    for s in TAGE_SPALTEN_ARTIKEL:
        anzeige_deckung[s] = anzeige_deckung[s].apply(_fmt_tage)
    for s in DATUM_SPALTEN_ARTIKEL:
        anzeige_deckung[s] = anzeige_deckung[s].apply(_fmt_datum)
    auswahl_ereignis = st.dataframe(
        anzeige_deckung.style.map(_faerbe(_AMPEL_FARBEN), subset=["Ampel"]),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="dispo_artikel_tabelle",
    )

    ausgewaehlte_zeilen = auswahl_ereignis.selection.rows if auswahl_ereignis else []
    if ausgewaehlte_zeilen:
        gewaehlt = deckung.iloc[ausgewaehlte_zeilen[0]]
        norm_nr = gewaehlt["Norm-Nr"]
        norm_nr_key = str(norm_nr)

        st.markdown(f"**Reichweite: {norm_nr} – {gewaehlt['Kurztext']}**")
        grafik_spalte, mail_spalte = st.columns([2, 1])

        with grafik_spalte:
            artikel_positionen = positionen[positionen["Norm-Nr"] == norm_nr].sort_values("Ladedatum")
            if artikel_positionen.empty:
                st.info("Keine Positionen fuer diesen Artikel gefunden.")
            else:
                verlauf = pd.concat([
                    pd.DataFrame({
                        "Ladedatum": artikel_positionen["Ladedatum"],
                        "Menge": artikel_positionen["Bestand verfügbar"]
                        + artikel_positionen["Zugang bis Ladedatum"],
                        "Reihe": "Verfügbare Deckung",
                    }),
                    pd.DataFrame({
                        "Ladedatum": artikel_positionen["Ladedatum"],
                        "Menge": artikel_positionen["Kum. Bedarf Artikel"],
                        "Reihe": "Kumulierter Bedarf",
                    }),
                ])
                chart = (
                    alt.Chart(verlauf)
                    .mark_line(point=True, strokeWidth=2.5)
                    .encode(
                        x=alt.X("Ladedatum:T", title="Ladedatum"),
                        y=alt.Y("Menge:Q", title="Menge"),
                        color=alt.Color(
                            "Reihe:N",
                            scale=alt.Scale(
                                domain=["Verfügbare Deckung", "Kumulierter Bedarf"],
                                range=["#3B82F6", "#EC4899"],
                            ),
                            legend=alt.Legend(title=None),
                        ),
                        tooltip=[
                            alt.Tooltip("Ladedatum:T", title="Ladedatum"),
                            alt.Tooltip("Reihe:N", title="Reihe"),
                            alt.Tooltip("Menge:Q", title="Menge", format=",.0f"),
                        ],
                    )
                    .properties(height=320)
                )
                st.altair_chart(chart, use_container_width=True)

        with mail_spalte:
            kontakte = st.session_state.setdefault("dispo_kontakte", lade_kontakte())
            neue_mail = st.text_input(
                "E-Mail Ansprechpartner",
                value=kontakte.get(norm_nr_key, ""),
                key=f"dispo_mail_{norm_nr_key}",
            )
            if st.button("E-Mail speichern", key=f"dispo_mail_speichern_{norm_nr_key}"):
                kontakte[norm_nr_key] = neue_mail
                speichere_kontakte(kontakte)
                st.session_state["dispo_kontakte"] = kontakte
                st.success("Gespeichert.")

    st.divider()
    _render_abbauplan(positionen)

    st.divider()
    _render_reichweite_tabelle(positionen)

    st.divider()

    # --- Positionen -----------------------------------------------------------
    st.subheader("Positionen")
    p1, p2, p3 = st.columns(3)
    pos_gefiltert = positionen
    with p1:
        pos_gefiltert = _filter_auswahl(pos_gefiltert, "Werk", "Werk", "positionen")
    with p2:
        pos_gefiltert = _filter_auswahl(pos_gefiltert, "Kunde", "Kunde", "positionen")
    with p3:
        pos_gefiltert = _filter_auswahl(pos_gefiltert, "Status", "Status", "positionen")
    _zeige_tabelle(
        pos_gefiltert, POSITIONEN_SPALTEN,
        menge_spalten=MENGEN_SPALTEN_POSITIONEN,
        tage_spalten=TAGE_SPALTEN_POSITIONEN,
        datum_spalten=DATUM_SPALTEN_POSITIONEN,
        farben={"Status": _STATUS_FARBEN, "Versandart": _VERSANDART_FARBEN},
    )

    st.divider()
    _render_export(positionen)
