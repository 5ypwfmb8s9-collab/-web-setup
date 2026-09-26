"""Design-System: CSS laden, Home-Bildschirm-Metadaten, Logo."""

from __future__ import annotations

import base64
import html
from functools import lru_cache
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = ROOT / "assets" / "styles.css"
ICON_PATH = ROOT / "static" / "kano-icon-512.png"

GRADIENT_STOPS = ["#2870EA", "#7B61FF", "#E3008C", "#FF8C00"]


@lru_cache(maxsize=1)
def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def inject_css() -> None:
    """Zentrales Stylesheet einbinden (muss bei jedem Skriptlauf passieren)."""
    st.html(f"<style>{_css()}</style>")


# Ergänzt <head> um Icon & Web-App-Metadaten, damit „Zum Home-Bildschirm“ gut aussieht.
# Auf Streamlit Community Cloud läuft die App in einem iframe; Safari/Chrome nehmen Icon und
# Namen aber von der äußeren Seite. Deshalb wird – soweit der Browser es erlaubt (gleiche
# Domain) – auch die äußere Seite angepasst. Das Icon ist als data-URL eingebettet, damit es
# unabhängig vom Pfad der Seite funktioniert.
_HEAD_JS = """
<span class="kano-invisible"></span>
<script>
(function () {
  const ICON_180 = "__ICON_180__";
  const ICON_192 = "__ICON_192__";
  const docs = [document];
  try { if (window.parent && window.parent !== window) docs.push(window.parent.document); } catch (e) {}
  try { if (window.top && window.top !== window && window.top !== window.parent) docs.push(window.top.document); } catch (e) {}
  docs.forEach(function (doc) {
    try {
      const head = doc.head;
      if (!head || head.querySelector('meta[name="kano-head"]')) return;
      // vorhandene (Streamlit-)Icons entfernen, damit unseres gewinnt
      head.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"], link[rel^="apple-touch-icon"], link[rel="manifest"]')
          .forEach(function (el) { el.remove(); });
      head.querySelectorAll('meta[name="apple-mobile-web-app-title"], meta[name="application-name"], meta[name="theme-color"]')
          .forEach(function (el) { el.remove(); });
      const add = function (tag, attrs) { const el = doc.createElement(tag);
        Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); }); head.prepend(el); };
      add('meta', {name: 'kano-head', content: '1'});
      add('link', {rel: 'apple-touch-icon', sizes: '180x180', href: ICON_180});
      add('link', {rel: 'icon', type: 'image/png', sizes: '192x192', href: ICON_192});
      add('meta', {name: 'apple-mobile-web-app-capable', content: 'yes'});
      add('meta', {name: 'mobile-web-app-capable', content: 'yes'});
      add('meta', {name: 'apple-mobile-web-app-title', content: 'KANO'});
      add('meta', {name: 'application-name', content: 'KANO'});
      add('meta', {name: 'apple-mobile-web-app-status-bar-style', content: 'black'});
      add('meta', {name: 'theme-color', content: '#000000'});
      doc.title = 'KANO';
      const vp = head.querySelector('meta[name="viewport"]');
      if (vp) vp.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');
    } catch (e) {}
  });
})();
</script>
"""


@lru_cache(maxsize=1)
def _head_js() -> str:
    def data_url(name: str) -> str:
        return "data:image/png;base64," + base64.b64encode((ROOT / "static" / name).read_bytes()).decode()

    return _HEAD_JS.replace("__ICON_180__", data_url("kano-icon-180.png")).replace("__ICON_192__", data_url("kano-icon-192.png"))


def inject_head() -> None:
    """Nur einmal pro Sitzung nötig – die Änderungen am <head> bleiben bestehen."""
    if st.session_state.get("_head_injected"):
        return
    st.session_state["_head_injected"] = True
    st.html(_head_js(), unsafe_allow_javascript=True)


def set_cookie(name: str, value: str, max_age: int) -> None:
    """Setzt ein Cookie im Browser (für „Angemeldet bleiben“)."""
    safe_name = html.escape(name)
    safe_value = html.escape(value)
    st.html(
        f"""<span class="kano-invisible"></span><script>
        document.cookie = "{safe_name}={safe_value}; Max-Age={int(max_age)}; Path=/; SameSite=Strict"
          + (location.protocol === 'https:' ? '; Secure' : '');
        </script>""",
        unsafe_allow_javascript=True,
    )


def delete_cookie(name: str) -> None:
    set_cookie(name, "", 0)


def logo_hero(tagline: str | None = None) -> None:
    st.html(
        f'<div style="text-align:center"><div class="kano-logo kano-hero-logo">KANO</div>'
        + (f'<div class="kano-tagline">{html.escape(tagline)}</div>' if tagline else "")
        + "</div>"
    )


def top_bar(right_text: str = "") -> None:
    st.html(
        f'<div class="kano-topbar"><span class="kano-logo">KANO</span>'
        f'<span class="kano-date">{html.escape(right_text)}</span></div>'
    )


def page_title(title: str, subtitle: str | None = None) -> None:
    st.html(
        f'<div class="kano-title">{html.escape(title)}</div>'
        + (f'<div class="kano-subtitle">{html.escape(subtitle)}</div>' if subtitle else "")
    )
