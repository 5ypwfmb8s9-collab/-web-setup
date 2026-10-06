"""
Dispositionslogik, unabhängig von Excel oder Oberfläche.
Dieselben Regeln stecken als Formeln im Excel-Report; das Dashboard in VWAI nutzt diese Funktionen.
"""
import numpy as np
import pandas as pd

from . import config


def zugang_vorbereiten(zugang, stichtag):
    """Ankunft gerechnet = max(geplante Ankunft, Stichtag); kumulierte Zugangsmenge je Artikel."""
    st = pd.Timestamp(stichtag)
    z = zugang.copy()
    z["Ankunft gerechnet"] = z["Geplante Ankunft"].where(z["Geplante Ankunft"] >= st, st)
    z["Kum. Zugang Artikel"] = z.groupby("Norm-Nr")["Menge"].cumsum()
    z["Hinweis"] = np.where(z["Geplante Ankunft"] < st, "Ankunft überfällig", "")
    return z


def berechne(bedarf, bestand_artikel, zugang, stichtag,
             rot=config.WARN_ROT_TAGE, gelb=config.WARN_GELB_TAGE):
    """
    bedarf: loaders.lade_bedarf (sortiert nach Artikel, Ladedatum)
    bestand_artikel: loaders.lade_bestand()[1]
    zugang: loaders.lade_zugang
    Rückgabe: (Positionen, Artikelübersicht, Zugänge vorbereitet)
    """
    st = pd.Timestamp(stichtag)
    z = zugang_vorbereiten(zugang, st)
    p = bedarf.copy()
    p["Bestand verfügbar"] = p["Norm-Nr"].map(bestand_artikel.set_index("Norm-Nr")["Verfügbar"]).fillna(0)

    # Zugang bis Ladedatum und "Gedeckt ab" je Einteilung
    zgr = {m: g for m, g in z.groupby("Norm-Nr")}
    zug_bis, gedeckt_ab = [], []
    p["Offene Menge"] = p["Bestellmenge"] - p["Geliefert"]
    p["Kum. Bedarf Artikel"] = p.groupby("Norm-Nr")["Offene Menge"].cumsum()
    for m, lade, kum, best in zip(p["Norm-Nr"], p["Ladedatum"], p["Kum. Bedarf Artikel"], p["Bestand verfügbar"]):
        g = zgr.get(m)
        if g is None:
            zug_bis.append(0)
            gedeckt_ab.append(pd.NaT)
            continue
        zug_bis.append(g.loc[g["Ankunft gerechnet"] <= lade, "Menge"].sum())
        noetig = kum - best
        treffer = g.loc[g["Kum. Zugang Artikel"] >= noetig, "Ankunft gerechnet"]
        gedeckt_ab.append(treffer.min() if len(treffer) else pd.NaT)
    p["Zugang bis Ladedatum"] = zug_bis

    p["Nicht zugewiesen"] = (p["Offene Menge"] - p["Zugewiesen offen"]).clip(lower=0)
    p["Tage bis Ladedatum"] = (p["Ladedatum"] - st).dt.days
    deckung = p["Bestand verfügbar"] + p["Zugang bis Ladedatum"]
    p["Fehlmenge"] = np.minimum(p["Offene Menge"], (p["Kum. Bedarf Artikel"] - deckung)).clip(lower=0)
    p["Gedeckt ab"] = pd.Series(gedeckt_ab, index=p.index).where(p["Fehlmenge"] > 0)
    p["Verspätung (Tage)"] = (p["Gedeckt ab"] - p["Ladedatum"]).dt.days

    def status(r):
        if r["Offene Menge"] <= 0:
            return "Erledigt"
        hat_zugang = pd.notna(r["Gedeckt ab"])
        if r["Ladedatum"] < st:
            if r["Fehlmenge"] <= 0:
                return "Rückstand gedeckt"
            return "Rückstand, Zugang kommt" if hat_zugang else "Rückstand ungedeckt"
        if r["Fehlmenge"] <= 0:
            return "Gedeckt"
        if hat_zugang:
            return "Zugang zu spät"
        return "Engpass" if r["Tage bis Ladedatum"] <= rot else "Fehlmenge später"

    p["Status"] = p.apply(status, axis=1)

    g = p.groupby("Norm-Nr")
    zsum = z.groupby("Norm-Nr")["Menge"].sum()
    znext = z.groupby("Norm-Nr")["Ankunft gerechnet"].min()
    a = pd.DataFrame({
        "Kurztext": g["Kurztext"].first(),
        "Kunden": g["Kunde"].agg(lambda s: ", ".join(sorted(set(s)))),
        "Bestand verfügbar": g["Bestand verfügbar"].first(),
        "Offene Menge gesamt": g["Offene Menge"].sum(),
        "Rückstand (Menge)": p[p["Ladedatum"] < st].groupby("Norm-Nr")["Offene Menge"].sum(),
        "Erste Fehlmenge am": p[p["Fehlmenge"] > 0].groupby("Norm-Nr")["Ladedatum"].min(),
    })
    a["Zugänge unterwegs"] = a.index.map(zsum).fillna(0)
    a["Nächster Zugang"] = a.index.map(znext)
    a["Rückstand (Menge)"] = a["Rückstand (Menge)"].fillna(0)
    a["Reichweite (Tage)"] = (a["Erste Fehlmenge am"] - st).dt.days
    a["Ampel"] = a["Reichweite (Tage)"].apply(
        lambda t: "Grün" if pd.isna(t) else ("Rot" if t <= rot else ("Gelb" if t <= gelb else "Grün")))
    a = a.reset_index().sort_values(["Erste Fehlmenge am", "Norm-Nr"], na_position="last").reset_index(drop=True)
    return p, a, z
