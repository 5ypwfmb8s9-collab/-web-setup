"""Wiederverwendbare UI-Bausteine im KANO-Stil."""

from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st

# --------------------------------------------------------------------------- Formatierung


def fmt_int(value: float | None) -> str:
    """Ganzzahl mit deutschem Tausenderpunkt: 1.234"""
    if value is None:
        return "–"
    return f"{int(round(value)):,}".replace(",", ".")


def fmt_num(value: float | None, digits: int = 1) -> str:
    """Kommazahl im deutschen Format: 72,4"""
    if value is None:
        return "–"
    return f"{value:.{digits}f}".replace(".", ",")


def esc(text: object) -> str:
    return html.escape(str(text))


# --------------------------------------------------------------------------- Grafische Elemente


def ring(value: float, target: float, *, center_value: str, unit: str, sub: str = "", size: int = 210) -> None:
    """Fortschrittsring mit Spectrum-Gradient (reines CSS: conic-gradient + Maske).

    Über 100 % bleibt der Ring einfach voll – bewusst ohne rote Warnfarbe.
    """
    ratio = 0 if target <= 0 else max(0.0, min(value / target, 1.0))
    p = ratio * 100
    if p <= 0.1:
        fill = "#161616"
    else:
        fill = (
            f"conic-gradient(#2870EA 0%, #7B61FF {p * 0.35:.2f}%, #E3008C {p * 0.7:.2f}%, "
            f"#FF8C00 {p:.2f}%, #161616 {p:.2f}% 100%)"
        )
    st.html(
        f"""<div class="kano-ring-wrap"><div class="kano-ring" style="width:{size}px;height:{size}px">
  <div class="track" style="background:{fill}"></div>
  <div class="center">
    <div class="value">{esc(center_value)}</div>
    <div class="unit">{esc(unit)}</div>
    {f'<div class="sub">{esc(sub)}</div>' if sub else ''}
  </div>
</div></div>"""
    )


def bar(label: str, value: float, target: float, unit: str = "g", show_numbers: bool = True) -> str:
    """HTML für einen Fortschrittsbalken (zum Kombinieren mehrerer Balken in einem st.html)."""
    pct = 0 if target <= 0 else max(0.0, min(value / target, 1.0)) * 100
    right = f"{fmt_int(value)} / {fmt_int(target)} {unit}" if show_numbers else ""
    return (
        f'<div class="kano-bar"><div class="row"><span>{esc(label)}</span><span>{esc(right)}</span></div>'
        f'<div class="track"><div class="fill" style="width:{pct:.1f}%"></div></div></div>'
    )


def bars(items: list[str]) -> None:
    st.html('<div class="kano-card">' + "".join(items) + "</div>")


@dataclass
class Stat:
    value: str
    label: str


def stats(items: list[Stat]) -> None:
    cols = max(1, min(len(items), 3))
    st.html(
        f'<div class="kano-stats" style="grid-template-columns:repeat({cols},1fr)">'
        + "".join(f'<div class="kano-stat"><div class="v">{esc(s.value)}</div><div class="l">{esc(s.label)}</div></div>' for s in items)
        + "</div>"
    )


def card(title: str | None, body_html: str, *, glow: bool = False) -> None:
    """Einfache Karte. `body_html` muss bereits escaped sein."""
    head = f"<h4>{esc(title)}</h4>" if title else ""
    st.html(f'<div class="kano-card{" glow" if glow else ""}">{head}{body_html}</div>')


def note(text: str, *, care: bool = False) -> None:
    """Neutraler Hinweis (niemals rot)."""
    st.html(f'<div class="kano-note{" care" if care else ""}">{text}</div>')


def label(text: str) -> None:
    st.html(f'<div class="kano-label">{esc(text)}</div>')


def item_rows(rows: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="kano-item"><span class="n">{esc(n)}</span><span class="d">{esc(d)}</span></div>' for n, d in rows)


# --------------------------------------------------------------------------- Navigation

NAV_ITEMS = [
    ("heute", "Heute", ":material/today:"),
    ("tracken", "Tracken", ":material/add_circle:"),
    ("plan", "Plan", ":material/restaurant_menu:"),
    ("fortschritt", "Fortschritt", ":material/monitoring:"),
    ("coach", "Coach", ":material/forum:"),
    ("profil", "Profil", ":material/person:"),
]


def bottom_nav(pages: dict, active_key: str) -> None:
    """Feste Navigation unten mit Icons. `pages` bildet Schlüssel → st.Page ab."""
    with st.container(key="kano_nav", horizontal=True):
        for key, label_text, icon in NAV_ITEMS:
            state = "active" if key == active_key else "idle"
            with st.container(key=f"nav_{state}_{key}"):
                st.page_link(pages[key], label=label_text, icon=icon)
