"""Tests fuer reklamation_logic.py (Ausfallfracht-Reklamationen)."""

from unittest.mock import Mock, patch

import pytest
import requests

from reklamation_logic import (
    STATUS_ERLEDIGT,
    STATUS_OFFEN,
    TYP_AUSFALLFRACHT,
    TYP_STORNO,
    Reklamation,
    ReklamationenError,
    fetch_reklamationen,
    get_configured_urls,
    update_status,
)


def _response(json_body=None, status_code=200, raise_exc=None):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_body

    def raise_for_status():
        if raise_exc:
            raise raise_exc

    resp.raise_for_status.side_effect = raise_for_status
    return resp


def test_fetch_reklamationen_parses_value_wrapped_list():
    payload = {
        "value": [
            {
                "id": "1",
                "Absender": "duvenbeck@example.com",
                "Title": "Ausfallfracht KW10",
                "Empfangsdatum": "2026-03-05T10:00:00Z",
                "Dateiname": "Ausfallfracht_0305.pdf",
                "DateiLink": "https://sharepoint.example/dok/Ausfallfracht_0305.pdf",
                "Status": "Offen",
            }
        ]
    }
    with patch("reklamation_logic.requests.get", return_value=_response(payload)):
        result = fetch_reklamationen("https://flow.example/list")

    assert result == [
        Reklamation(
            id="1",
            absender="duvenbeck@example.com",
            betreff="Ausfallfracht KW10",
            empfangsdatum="2026-03-05T10:00:00Z",
            dateiname="Ausfallfracht_0305.pdf",
            dateilink="https://sharepoint.example/dok/Ausfallfracht_0305.pdf",
            status="Offen",
        )
    ]


def test_fetch_reklamationen_ohne_typ_feld_faellt_auf_ausfallfracht_zurueck():
    payload = {
        "value": [
            {
                "id": "1",
                "Absender": "noreply@duvenbeck.de",
                "Title": "Rechnung Ausfallfracht zu Frachtbrief",
                "Empfangsdatum": "2026-03-05T10:00:00Z",
                "Dateiname": "Ausfallfracht_0305.pdf",
                "DateiLink": "https://sharepoint.example/dok/Ausfallfracht_0305.pdf",
                "Status": "Offen",
            }
        ]
    }
    with patch("reklamation_logic.requests.get", return_value=_response(payload)):
        result = fetch_reklamationen("https://flow.example/list")

    assert result[0].typ == TYP_AUSFALLFRACHT


def test_fetch_reklamationen_erkennt_storno_typ():
    payload = {
        "value": [
            {
                "id": "3",
                "Absender": "ausfallfrachten-herne@duvenbeck.de",
                "Title": "Storno Ausfallfracht KW10",
                "Empfangsdatum": "2026-03-06T10:00:00Z",
                "Dateiname": "Storno_0306.pdf",
                "DateiLink": "https://sharepoint.example/dok/Storno_0306.pdf",
                "Status": "Offen",
                "Typ": "Storno",
            }
        ]
    }
    with patch("reklamation_logic.requests.get", return_value=_response(payload)):
        result = fetch_reklamationen("https://flow.example/list")

    assert result[0].typ == TYP_STORNO
    assert result[0].absender == "ausfallfrachten-herne@duvenbeck.de"


def test_fetch_reklamationen_accepts_plain_list():
    payload = [
        {
            "id": "2",
            "Absender": "a@b.de",
            "Title": "X",
            "Empfangsdatum": "2026-01-01",
            "Dateiname": "y.pdf",
            "DateiLink": "https://x",
            "Status": "",
        }
    ]
    with patch("reklamation_logic.requests.get", return_value=_response(payload)):
        result = fetch_reklamationen("https://flow.example/list")

    assert result[0].status == STATUS_OFFEN  # leerer Status -> Standard "Offen"


def test_fetch_reklamationen_ohne_url_wirft_fehler():
    with pytest.raises(ReklamationenError):
        fetch_reklamationen("")


def test_fetch_reklamationen_netzwerkfehler_wird_verstaendlich():
    with patch(
        "reklamation_logic.requests.get",
        side_effect=requests.ConnectionError("boom"),
    ):
        with pytest.raises(ReklamationenError):
            fetch_reklamationen("https://flow.example/list")


def test_fetch_reklamationen_unerwartetes_format():
    with patch("reklamation_logic.requests.get", return_value=_response({"foo": "bar"})):
        with pytest.raises(ReklamationenError):
            fetch_reklamationen("https://flow.example/list")


def test_update_status_sendet_id_und_status():
    mock_response = _response({"ok": True})
    with patch("reklamation_logic.requests.post", return_value=mock_response) as mock_post:
        update_status("https://flow.example/update", "1", STATUS_ERLEDIGT)

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"id": "1", "status": STATUS_ERLEDIGT}


def test_update_status_lehnt_unbekannten_status_ab():
    with pytest.raises(ReklamationenError):
        update_status("https://flow.example/update", "1", "Sonstwas")


def test_update_status_http_fehler_wird_verstaendlich():
    error_response = _response(raise_exc=requests.HTTPError("500"))
    with patch("reklamation_logic.requests.post", return_value=error_response):
        with pytest.raises(ReklamationenError):
            update_status("https://flow.example/update", "1", STATUS_OFFEN)


def test_get_configured_urls_vollstaendig():
    secrets = {"reklamationen": {"list_url": "https://a", "update_url": "https://b"}}
    assert get_configured_urls(secrets) == {"list_url": "https://a", "update_url": "https://b"}


def test_get_configured_urls_fehlend():
    assert get_configured_urls({}) is None
    assert get_configured_urls({"reklamationen": {"list_url": "https://a"}}) is None


def test_get_configured_urls_bei_beliebigem_fehler_beim_zugriff():
    class ExplodingSecrets:
        def __getitem__(self, key):
            raise RuntimeError("keine secrets.toml vorhanden")

    assert get_configured_urls(ExplodingSecrets()) is None
