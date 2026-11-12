"""Reiter "EDI Veränderung" im Dashboard Dispo: Bedarfsexport von heute mit dem
vom Vortag vergleichen, Änderungen kategorisiert anzeigen und je Änderung eine
E-Mail-Vorlage im Standard-Mailprogramm (Outlook) öffnen. Rechnung in
edi_vergleich.py."""
from __future__ import annotations

import io

import altair as alt
import pandas as pd
import streamlit as st

import edi_vergleich as ev
from dispo_dashboard import loaders

_ZEIGE_SPALTEN = ["Bewertung", "E-Mail", "Änderung", "Norm-Nr", "Teil (Kunde)", "Kunde", "Werk", "Abladestelle",
                  "Mehr", "Vorgezogen", "Verschoben", "Weniger", "Erster Termin", "Fehlmenge", "Details"]
_MENGEN = ("Mehr", "Vorgezogen", "Verschoben", "Weniger", "Fehlmenge")


def _menge(wert) -> str:
    if wert is None or pd.isna(wert) or abs(float(wert)) < 1e-9:
        return ""
    return f"{float(wert):,.0f}".replace(",", ".")


def _datum(wert) -> str:
    return "" if wert is None or pd.isna(wert) else f"{pd.Timestamp(wert):%d.%m.%Y}"


def _vortag_aus_upload(datei) -> dict | None:
    try:
        df = loaders.lade_bedarf(io.BytesIO(datei.getvalue()))
    except Exception as exc:   # falsche Datei - nicht abstuerzen
        st.error(f"Das ist kein Bedarfsexport (oder die Datei ist beschädigt): {exc}")
        return None
    datum = ev.datum_aus_name(datei.name)
    if datum is None:
        datum = st.date_input("Datenstand dieser Datei", value=pd.Timestamp.today().date() - pd.Timedelta(days=1),
                              format="DD.MM.YYYY", key="edi_vortag_datum")
    return {"df": df, "datum": datum, "name": datei.name}


def _abrufkurve(kurve: dict, stichtag: pd.Timestamp) -> alt.Chart:
    """Kumulierte offene Menge je Ladedatum: Vortag (grau) gegen heute (blau).
    Liegt die blaue Linie hoeher, braucht der Kunde bis dahin mehr bzw. frueher."""
    termine = sorted(set(kurve["alt"]) | set(kurve["neu"]))
    if not termine:
        return alt.Chart(pd.DataFrame())
    spanne = max((termine[-1] - termine[0]).days, 1)
    rand = pd.Timedelta(days=max(2, round(spanne * 0.08)))
    zeilen = []
    for name, werte in (("Vortag", kurve["alt"]), ("Heute", kurve["neu"])):
        summe = 0.0
        zeilen.append({"Termin": termine[0] - rand, "Kumuliert": 0.0, "Abruf": name})
        for d in termine:
            summe += werte.get(d, 0.0)
            zeilen.append({"Termin": d, "Kumuliert": summe, "Abruf": name})
        zeilen.append({"Termin": termine[-1] + rand, "Kumuliert": summe, "Abruf": name})   # Endstand sichtbar
    df = pd.DataFrame(zeilen)
    achse = alt.Axis(format="%d.%m.", grid=False,
                     tickCount={"interval": "day", "step": 1} if spanne <= 14 else
                     {"interval": "week", "step": 1} if spanne <= 120 else {"interval": "month", "step": 1})
    return alt.Chart(df).mark_line(interpolate="step-after", strokeWidth=2.5).encode(
        x=alt.X("Termin:T", title=f"Ladedatum (bis {stichtag:%d.%m.} = sofort)", axis=achse),
        y=alt.Y("Kumuliert:Q", title="Stück kumuliert"),
        color=alt.Color("Abruf:N", scale=alt.Scale(domain=["Vortag", "Heute"], range=["#94a3b8", "#2563eb"]),
                        legend=alt.Legend(title=None, orient="bottom")),
        strokeDash=alt.StrokeDash("Abruf:N", scale=alt.Scale(domain=["Vortag", "Heute"], range=[[5, 4], [1, 0]]),
                                  legend=None),
        tooltip=[alt.Tooltip("Abruf:N"), alt.Tooltip("Termin:T", format="%d.%m.%Y"),
                 alt.Tooltip("Kumuliert:Q", format=",.0f")],
    ).properties(height=240)


def _render_kennzahlen(ergebnis: dict) -> None:
    z = ergebnis["zusammenfassung"]
    spalten = st.columns(6)
    for spalte, k in zip(spalten, ("erhoehung", "vorgezogen", "neu", "verschoben", "reduziert", "entfallen")):
        info = ev.KATEGORIEN[k]
        spalte.metric(f"{info['icon']} {info['de']}", z[k]["lieferplaene"],
                      f"{_menge(z[k]['menge']) or '0'} Stk", delta_color="off", delta_arrow="off",
                      help=f"Anzahl Lieferpläne · Menge. {info['hilfe']}")
    hinweise = []
    if z["unklar"]["lieferplaene"]:
        hinweise.append(f"❔ Einteilungen der nächsten Tage weggefallen – vorab versendet oder vom Kunden gestrichen? "
                        f"{z['unklar']['lieferplaene']} Lieferpläne, {_menge(z['unklar']['menge'])} Stück (in der Liste)")
    if z["versendet"]["lieferplaene"]:
        hinweise.append(f"✔️ Rückstand/heute weggefallen (vermutlich versendet, keine EDI-Änderung): "
                        f"{z['versendet']['lieferplaene']} Lieferpläne, {_menge(z['versendet']['menge'])} Stück")
    for h in hinweise:
        st.caption(h)


def _render_mail(ergebnis: dict, lieferplaene: list, sprache: str, beschriftung: str) -> None:
    m = ev.mail_entwurf(ergebnis, lieferplaene, sprache)
    if not m["mailto"]:
        st.caption("Keine EDI-Änderung – keine Mail nötig.")
        return
    st.link_button(beschriftung, m["mailto"], type="primary", use_container_width=True)
    st.caption(f"Öffnet dein Mailprogramm (Outlook) mit Betreff und Text · CC {m['cc']}"
               + (f" · An: {m['an']}" if m["an"] else " · Empfänger trägst du selbst ein"))
    if m["gekuerzt"]:
        st.warning("Die Mail ist für einen Link zu lang – im Outlook-Entwurf stehen nicht alle Teile. "
                   "Den vollständigen Text unten kopieren und einfügen.")
    with st.expander("Text ansehen / kopieren", expanded=m["gekuerzt"]):
        st.code(f"Betreff: {m['betreff']}\n\n{m['text']}", language=None, wrap_lines=True)


def _render_detail(ergebnis: dict, zeile: pd.Series, sprache: str) -> None:
    lp = zeile["Lieferplan"]
    teil = zeile["Teil (Kunde)"] or zeile["Norm-Nr"]
    st.markdown(f"##### {zeile['Bewertung']} · {teil} · Norm-Nr {zeile['Norm-Nr']}")
    st.caption(f"{zeile['Kunde']} · Werk {zeile['Werk'] or '–'} · Abladestelle {zeile['Abladestelle'] or '–'} · "
               f"Lieferplan {lp} · {zeile['Kurztext']}")
    if zeile["Fehlmenge"] > 0:
        st.error(f"Mit dem neuen Abruf fehlen für diesen Lieferplan {_menge(zeile['Fehlmenge'])} Stück "
                 f"(erste Fehlmenge Ladedatum {_datum(zeile['Erster Fehltag'])}) – weder Bestand noch Zugang reicht.")
    links, rechts = st.columns([3, 2])
    with links:
        ereignisse = ergebnis["ereignisse"]
        g = ereignisse[ereignisse["Lieferplan"] == lp]
        tabelle = pd.DataFrame({
            "Art": g["Kategorie"].map(lambda k: f"{ev.KATEGORIEN[k]['icon']} {ev.KATEGORIEN[k]['de']}"),
            "Termin vorher": g["Datum alt"].map(_datum),
            "Termin jetzt": g["Datum neu"].map(_datum),
            "Menge": g["Menge"].map(_menge),
            "Änderung": g["Text"],
        })
        st.dataframe(tabelle, hide_index=True, use_container_width=True)
        st.markdown("**Abrufkurve** – kumulierte offene Menge: grau = Vortag, blau = heute. Liegt Blau höher, "
                    "braucht der Kunde bis dahin mehr bzw. früher.")
        st.altair_chart(_abrufkurve(ergebnis["kurven"].get(lp, {"alt": {}, "neu": {}}), ergebnis["stichtag_neu"]),
                        use_container_width=True)
    with rechts:
        st.markdown("**Reagieren**")
        _render_mail(ergebnis, [lp], sprache, "✉️ E-Mail in Outlook öffnen")


def render_edi_tab(daten: dict) -> None:
    stichtag = pd.Timestamp(daten["stichtag"])
    st.markdown("#### EDI Veränderung – was hat der Kunde seit dem letzten Export geändert?")
    st.caption(
        "Vergleicht den Bedarfsexport von heute mit dem vom Vortag – je Lieferplan (Artikel × Werk × "
        "Abladestelle) und Ladedatum. Jede Änderung wird eingeordnet: ⬆️ Erhöhung · ⏪ vorgezogen · 🆕 neuer "
        "Lieferplan · ⏩ nach hinten verschoben · ⬇️ reduziert / rausgenommen · ❌ Lieferplan entfallen. Was vorne "
        "wegfällt, weil wir es versendet haben, zählt nicht als Änderung (✔️). Zu jeder Änderung gibt es eine "
        "E-Mail-Vorlage, die sich direkt in Outlook öffnet."
    )

    vortag = daten.get("bedarf_vortag")
    with st.expander("Vortages-Export selbst hochladen" + (" (optional)" if vortag else ""), expanded=vortag is None):
        datei = st.file_uploader("Bedarfsexport vom Vortag bzw. letzten Arbeitstag (SAP-Export EXPORT_JJJJMMTT_…)",
                                 type=["xlsx"], key="edi_vortag_upload")
    if datei is not None:
        vortag = _vortag_aus_upload(datei) or vortag
    if vortag is None:
        st.info(
            "So geht's: Lade unten bei „Daten aktualisieren“ **beide Bedarfsexporte** hoch – den von heute und den "
            "vom Vortag (zusammen mit Bestand und Zugängen). DISPO PRO erkennt am Dateinamen "
            "(EXPORT_JJJJMMTT_…), welcher der neue ist, und vergleicht automatisch. Oder den Vortages-Export "
            "hier oben hochladen."
        )
        return
    datum_alt = pd.Timestamp(vortag["datum"])
    if datum_alt >= stichtag:
        st.warning(f"Der Vergleichs-Export ({vortag['name']}) ist nicht älter als der heutige "
                   f"({stichtag:%d.%m.%Y}). Bitte den Export vom Vortag hochladen.")
        return

    c1, c2, c3 = st.columns(3)
    reaktion = int(c1.number_input("Kurzfristig = Termin innerhalb (Tage)", min_value=1, max_value=60,
                                   value=ev.STANDARD_REAKTION_TAGE, key="edi_reaktion",
                                   help="Erhöhungen/Vorziehungen bis dahin gelten als kurzfristig (🟠/🔴)."))
    sprache = c2.radio("Sprache der E-Mail", ["Deutsch", "English"], horizontal=True, key="edi_sprache")
    sprache = "EN" if sprache == "English" else "DE"
    versendete = c3.checkbox("Versendete (keine EDI-Änderung) auch zeigen", key="edi_versendete")

    bedarf_heute = daten.get("bedarf")
    if bedarf_heute is None:
        bedarf_heute = daten["positionen"]
    ergebnis = ev.vergleiche(vortag["df"], bedarf_heute, datum_alt, stichtag, daten.get("positionen"), reaktion)

    abstand = (stichtag - datum_alt).days
    st.caption(f"Vergleich: {vortag['name']} ({datum_alt:%d.%m.%Y}) → heute ({stichtag:%d.%m.%Y})"
               + (f" · {abstand} Tage Abstand – alle Änderungen dazwischen zusammengefasst" if abstand > 1 else "")
               + f" · verglichen bis Ladedatum {ergebnis['grenze']:%d.%m.%Y}")
    if ergebnis["grenze"] < stichtag + pd.Timedelta(days=28):
        st.warning(
            f"⚠️ Die Bedarfsexporte reichen nur bis {ergebnis['grenze']:%d.%m.%Y}. Änderungen danach sind nicht zu "
            "sehen. Für die EDI-Kontrolle den Bedarf in SAP jeden Tag mit **gleicher Auswahl und langem Zeitraum** "
            "ziehen (z. B. Ladedatum bis +6 Monate)."
        )

    _render_kennzahlen(ergebnis)
    lp_df = ergebnis["lieferplaene"]
    if not versendete:
        lp_df = lp_df[lp_df["Rang"] < 4]
    if lp_df.empty:
        st.success(f"✅ Keine EDI-Änderungen seit {datum_alt:%d.%m.%Y}.")
        return

    f1, f2, f3 = st.columns([2, 2, 2])
    kategorien = [k for k in ev.KATEGORIEN if k != "versendet" or versendete]
    gewaehlt = f1.multiselect("Art der Änderung", kategorien, default=kategorien, key="edi_filter_art",
                              placeholder="Art wählen",
                              format_func=lambda k: f"{ev.KATEGORIEN[k]['icon']} {ev.KATEGORIEN[k]['de']}")
    werke = sorted({str(w) for w in lp_df["Werk"] if str(w)})
    werk_filter = f2.multiselect("Werk", werke, key="edi_filter_werk", placeholder="alle Werke")
    suche = f3.text_input("Suche (Norm-Nr, Teil, Kunde)", key="edi_suche").strip().lower()
    lp_df = lp_df[lp_df["Kategorien"].map(lambda ks: any(k in gewaehlt for k in ks))]
    if werk_filter:
        lp_df = lp_df[lp_df["Werk"].astype(str).isin(werk_filter)]
    if suche:
        text = (lp_df["Norm-Nr"].astype(str) + " " + lp_df["Teil (Kunde)"] + " " + lp_df["Teil (Kunde)"].str.replace(" ", "")
                + " " + lp_df["Kunde"]).str.lower()
        lp_df = lp_df[text.str.contains(suche, regex=False)]
    lp_df = lp_df.reset_index(drop=True)
    if lp_df.empty:
        st.info("Keine Änderung passt zum Filter.")
        return

    anzeige = lp_df.copy()
    anzeige["E-Mail"] = [ev.mail_entwurf(ergebnis, [lp], sprache)["mailto"] for lp in lp_df["Lieferplan"]]
    for s in _MENGEN:
        anzeige[s] = anzeige[s].map(_menge)
    anzeige["Erster Termin"] = anzeige["Erster Termin"].map(_datum)
    st.caption("🔴 Handeln = mehr/früher innerhalb der Reaktionszeit und jetzt Fehlmenge · 🟠 Prüfen = kurzfristig "
               "mehr/früher oder Fehlmenge · 🔵 Info = später oder weniger. Zeile anklicken → Details, Abrufkurve, "
               "Mail. ✉️ öffnet die Mail direkt.")
    auswahl = st.dataframe(
        anzeige[_ZEIGE_SPALTEN], hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="single-row", key="edi_tabelle",
        height=min(38 + 35 * len(anzeige), 560),
        column_config={
            "E-Mail": st.column_config.LinkColumn("E-Mail", display_text="✉️ Mail", width="small"),
            "Details": st.column_config.TextColumn("Details", width="large"),
            "Änderung": st.column_config.TextColumn("Änderung", width="medium"),
            "Fehlmenge": st.column_config.TextColumn("Fehlmenge jetzt", help="Fehlmenge dieses Lieferplans im neuen "
                                                     "Stand (weder Bestand noch Zugang reicht)"),
        },
    )
    zeilen = auswahl.selection.rows if auswahl else []
    if zeilen:
        st.divider()
        _render_detail(ergebnis, lp_df.iloc[zeilen[0]], sprache)

    st.divider()
    s1, s2 = st.columns([3, 2])
    with s1:
        st.markdown("**Sammel-Mail für ein ganzes Werk**")
        gruppen = lp_df[lp_df["Rang"] < 4].groupby(["Kunde", "Werk"], sort=False)["Lieferplan"].apply(list)
        if gruppen.empty:
            st.caption("Keine EDI-Änderungen im Filter.")
        else:
            optionen = list(gruppen.index)
            wahl = st.selectbox("Werk", optionen, key="edi_sammel_werk",
                                format_func=lambda o: f"{o[0]} · Werk {o[1] or '–'} ({len(gruppen[o])} "
                                                      f"{'Teil' if len(gruppen[o]) == 1 else 'Teile'})")
            _render_mail(ergebnis, gruppen[wahl], sprache, "✉️ Sammel-Mail in Outlook öffnen")
    with s2:
        st.markdown("**Für die Ablage**")
        st.download_button("📥 Änderungen als Excel", data=ev.erstelle_excel(ergebnis),
                           file_name=ev.dateiname(stichtag), key="edi_download",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("So wird verglichen – und was du in SAP ziehen musst"):
        st.markdown(
            "- **Zwei Bedarfsexporte reichen:** der von heute und der vom Vortag (montags der vom Freitag). Beide "
            "mit **derselben Auswahl** und einem **langen Zeitraum** (z. B. Ladedatum bis +6 Monate) – "
            "verglichen wird nur, was beide Exporte abdecken.\n"
            "- Verglichen wird je **Lieferplan** (Artikel × Werk × Abladestelle) die **offene Menge je "
            "Ladedatum**. Termine bis heute zählen als „sofort“ – ein Rückstand, den der Kunde nur umdatiert, "
            "ist keine Änderung.\n"
            "- ❔ **Weggefallen – versendet?** Fällt eine Einteilung der nächsten 3 Tage vorne weg, kann das "
            "unser vorgezogener Versand sein – oder der Kunde hat sie gestrichen. Das lässt sich aus den Exporten "
            "nicht unterscheiden; du weißt, was raus ist.\n"
            "- **Unser Versand** nimmt immer von vorne weg (älteste Einteilung zuerst). Was vorne fehlt, steht "
            "als ✔️ „versendet“ und ist keine EDI-Änderung. Hat der Kunde einen Rückstand gestrichen, sieht das "
            "genauso aus – deshalb „vermutlich“.\n"
            "- Gleiche Menge an einem Termin weg und an einem anderen dazu = **Verschiebung** (⏪ vorgezogen / "
            "⏩ nach hinten). Was übrig bleibt, ist ⬆️ **Erhöhung** bzw. ⬇️ **Reduzierung**. Ein ganz neuer "
            "Lieferplan ist 🆕, ein ganz verschwundener ❌.\n"
            "- **Bewertung:** 🔴 mehr/früher innerhalb der Reaktionszeit und der Lieferplan hat jetzt Fehlmenge · "
            "🟠 kurzfristig mehr/früher oder Fehlmenge · 🔵 später, weniger oder langfristig gedeckt.\n"
            "- **Mail:** öffnet eine neue Mail im Standard-Mailprogramm (Outlook muss in Windows als "
            "Standard-Mail-App eingestellt sein). CC Dispo@normgmbh.de ist gesetzt, den Empfänger trägst du ein."
        )
