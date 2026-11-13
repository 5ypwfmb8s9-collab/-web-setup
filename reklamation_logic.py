"""Ausfallfracht-Reklamationen: Abruf und Status-Pflege ueber Power Automate.

Die eigentlichen Daten liegen in einer SharePoint-Liste, die zwei Power-
Automate-Flows befuellen: Ausfallfracht-Rechnungen (Absender
noreply@duvenbeck.de, Betreff "Rechnung Ausfallfracht zu Frachtbrief")
und Storno-PDFs dazu (Absender ausfallfrachten-herne@duvenbeck.de). Jede
Reklamation traegt ein ``typ``-Feld (TYP_AUSFALLFRACHT/TYP_STORNO), um
beide Faelle im Dashboard zu unterscheiden. Dieses Modul spricht NICHT
direkt mit SharePoint/Graph, sondern mit zwei HTTP-getriggerten Flows,
die die dafuer noetigen, bereits im Tenant freigegebenen Connectors
verwenden:

- ``list_url``:   GET/POST ohne Body -> liefert alle Reklamationen als JSON.
- ``update_url``: POST {"id": ..., "status": ...} -> setzt den Status einer
  Reklamation und liefert die aktualisierte Reklamation als JSON zurueck.

Beide URLs sind geheim (sie enthalten eine Signatur, die wie ein Passwort
wirkt) und werden daher nicht im Code, sondern in ``st.secrets``
(``.streamlit/secrets.toml``, nicht eingecheckt) hinterlegt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

STATUS_OFFEN = "Offen"
STATUS_IN_BEARBEITUNG = "In Bearbeitung"
STATUS_ERLEDIGT = "Erledigt"
STATUS_OPTIONS = [STATUS_OFFEN, STATUS_IN_BEARBEITUNG, STATUS_ERLEDIGT]

TYP_AUSFALLFRACHT = "Ausfallfracht"
TYP_STORNO = "Storno"
TYP_OPTIONS = [TYP_AUSFALLFRACHT, TYP_STORNO]

REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class Reklamation:
    id: str
    absender: str
    betreff: str
    empfangsdatum: str
    dateiname: str
    dateilink: str
    status: str
    typ: str = TYP_AUSFALLFRACHT


class ReklamationenError(RuntimeError):
    """Verstaendliche Fehlermeldung fuer die Streamlit-Oberflaeche."""


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_entry(raw: Dict[str, Any]) -> Reklamation:
    return Reklamation(
        id=_as_str(raw.get("id") or raw.get("ID") or raw.get("Id")),
        absender=_as_str(raw.get("Absender") or raw.get("absender")),
        betreff=_as_str(raw.get("Title") or raw.get("Betreff") or raw.get("betreff")),
        empfangsdatum=_as_str(raw.get("Empfangsdatum") or raw.get("empfangsdatum")),
        dateiname=_as_str(raw.get("Dateiname") or raw.get("dateiname")),
        dateilink=_as_str(raw.get("DateiLink") or raw.get("dateilink")),
        status=_as_str(raw.get("Status") or raw.get("status")) or STATUS_OFFEN,
        typ=_as_str(raw.get("Typ") or raw.get("typ")) or TYP_AUSFALLFRACHT,
    )


def _extract_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("value", "items", "Items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ReklamationenError(
        "Unerwartetes Antwortformat vom Abruf-Flow (keine Liste gefunden)."
    )


def fetch_reklamationen(list_url: str) -> List[Reklamation]:
    """Ruft alle Ausfallfracht-Reklamationen ueber den Abruf-Flow ab."""
    if not list_url:
        raise ReklamationenError("Keine list_url konfiguriert.")

    try:
        response = requests.get(list_url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ReklamationenError(f"Abruf fehlgeschlagen: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ReklamationenError("Antwort war kein gueltiges JSON.") from exc

    entries = _extract_list(payload)
    return [_parse_entry(e) for e in entries]


def update_status(update_url: str, reklamation_id: str, new_status: str) -> None:
    """Setzt den Status einer Reklamation ueber den Update-Flow."""
    if not update_url:
        raise ReklamationenError("Keine update_url konfiguriert.")
    if new_status not in STATUS_OPTIONS:
        raise ReklamationenError(f"Unbekannter Status: {new_status!r}")

    try:
        response = requests.post(
            update_url,
            json={"id": reklamation_id, "status": new_status},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ReklamationenError(f"Status-Update fehlgeschlagen: {exc}") from exc


def get_configured_urls(secrets: Any) -> Optional[Dict[str, str]]:
    """Liest list_url/update_url aus st.secrets, falls vorhanden.

    Bewusst breites except: st.secrets wirft je nach Streamlit-Version
    unterschiedliche Fehler (u.a. StreamlitSecretNotFoundError), wenn gar
    keine secrets.toml existiert - das soll hier immer als "nicht
    konfiguriert" behandelt werden, nicht als Absturz.
    """
    try:
        section = secrets["reklamationen"]
    except Exception:
        return None

    list_url = section.get("list_url")
    update_url = section.get("update_url")
    if not list_url or not update_url:
        return None
    return {"list_url": list_url, "update_url": update_url}
