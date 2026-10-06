"""
Zentrale Einstellungen: Spaltenzuordnung der SAP-Exporte und Geschäftsregeln.
Ändert sich ein Export-Layout in SAP, wird nur diese Datei angepasst.
"""

# ---------------------------------------------------------------------------
# Datei 1: Bedarfe – Lieferplan-Einteilungen (SAP-Export, türkische Spalten)
# ---------------------------------------------------------------------------
BEDARF_SPALTEN = {
    "Ad 1": "Kunde",
    "Malı teslim alan": "Warenempfänger",
    "Müşteri": "2er-Nr",                 # gebündelte Schlüsselnummer für Orte
    "Muhatap tanımı": "Werk",            # Kundenwerk
    "Teslimat yeri": "Abladestelle",
    "SD belgesi": "Lieferplan",
    "Termin satır no.": "Einteilung",
    "Malzeme": "Norm-Nr",
    "Müşteri malzemesi": "Kundenmaterial",
    "Malzeme kısa metni": "Kurztext",
    "Mlz.hazıredim tarihi": "Ladedatum",
    "Termin Tarihi": "Wunschtermin",     # gewünschtes Lieferdatum
    "Sipariş miktarı": "Bestellmenge",
    "Teslimat Miktarı": "Geliefert",
    "Açık Teyit": "Zugewiesen offen",
}

# ---------------------------------------------------------------------------
# Datei 2: Bestand – EWM-Bestandsliste je Charge / Lagerplatz
# ---------------------------------------------------------------------------
BESTAND_SPALTEN = {
    "Ürün": "Norm-Nr",
    "Ürün tanımı": "Kurztext",
    "Miktar": "Menge",
    "Stok türü": "Bestandsart",
    "Depo tipi": "Lagertyp",
    "Parti": "Charge",
    "Mal giriş tarihi": "WE-Datum",
}

# Bestandsarten, die als verfügbar gerechnet werden (Reihenfolge = Spalten im Report)
BESTAND_VERFUEGBAR = {
    "F2": "Frei verwendbar",
    "F1": "Angekommen, nicht eingelagert",
}
# Bestandsarten, die nur zur Info angezeigt, aber NICHT gerechnet werden
BESTAND_INFO = {
    "K2": "Gesperrt",
}
# Alle anderen Bestandsarten (z. B. D2) werden ignoriert.

# ---------------------------------------------------------------------------
# Datei 3: Zugänge – Transporte zu uns (SAP ZMM1000)
# Hauptpositionen haben Menge 0, die Mengen stehen in den Chargen-Unterpositionen.
# ---------------------------------------------------------------------------
ZUGANG_SPALTEN = {
    "Nakliye numarası": "Transport",
    "Referans": "Referenz",                 # Referenznummer der Lieferung zu uns
    "Ad 1": "Spediteur",
    "Teslimat": "Lieferung",
    "Referans belge": "Referenzbeleg",
    "Malzeme": "Norm-Nr",
    "Plnln.nakliye sonu": "Geplante Ankunft",  # geplantes Ankunftsdatum bei uns
    "Teslimat miktarı": "Menge",
}

# ---------------------------------------------------------------------------
# Datei 4: Stock Report des Versenders (nur Nebeninfo, geht NICHT in die Rechnung ein)
# Blatt "Format", Kopfzeile in Zeile 2. Rechts von "Müşteri Grubu" stehen Notizspalten,
# die neueste links ("28.09 notlar", "21.09 notlar - toplantı", ...).
# ---------------------------------------------------------------------------
STOCKREPORT_BLATT = "Format"
STOCKREPORT_KOPFZEILE = 1   # 0-basiert -> Zeile 2
STOCKREPORT_SPALTEN = {
    "Malzeme": "Norm-Nr",
    "Malzeme kısa metni": "Kurztext",
    "Müşteri malzemesi": "Kundenmaterial",
    "Stok yeterliği": "Reichweite lt. Report",
    "Tahditsiz klnb.": "Frei beim Versender",
    "Sipariş miktarı": "Auftragsmenge lt. Report",
    "Yolda": "Unterwegs lt. Report",
    "2Hafta": "Saldo nach 2 Wo",
    "4Hafta": "Saldo nach 4 Wo",
    "6Hafta": "Saldo nach 6 Wo",
    "8Hafta": "Saldo nach 8 Wo",
    "10Hafta": "Saldo nach 10 Wo",
    "12Hafta": "Saldo nach 12 Wo",
    "Lojistik Temsilcisi": "Verantwortlich",
    "Müşteri Grubu": "Kundengruppe",
}
STOCKREPORT_LETZTE_STAMMSPALTE = "Müşteri Grubu"

# Ab diesem Alter (Tage vor Stichtag) gilt eine Quelle als veraltet
QUELLE_VERALTET_TAGE = 1

# ---------------------------------------------------------------------------
# Geschäftsregeln
# ---------------------------------------------------------------------------
WARN_ROT_TAGE = 14     # Fehlmenge innerhalb dieser Tage -> Rot / "Engpass"
WARN_GELB_TAGE = 30    # Fehlmenge innerhalb dieser Tage -> Gelb
WOCHEN_VORSCHAU = 12   # Spalten im Reiter "Bedarf je Woche"
# Rückstand = Ladedatum < Stichtag und offene Menge > 0
# Zugänge mit geplanter Ankunft vor dem Stichtag (noch nicht empfangen) zählen ab Stichtag.
# Ein Zugang zählt für eine Einteilung, wenn er spätestens am Ladedatum ankommt.
