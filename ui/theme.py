"""Design-System: CSS laden, Home-Bildschirm-Metadaten, Logo."""

from __future__ import annotations

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
_HEAD_JS = """
<span class="kano-invisible"></span>
<script>
(function () {
  const head = document.head;
  if (head.querySelector('meta[name="kano-head"]')) return;
  const add = (tag, attrs) => { const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v)); head.appendChild(el); };
  add('meta', {name: 'kano-head', content: '1'});
  add('link', {rel: 'apple-touch-icon', sizes: '180x180', href: '/app/static/kano-icon-180.png'});
  add('link', {rel: 'icon', type: 'image/png', sizes: '192x192', href: '/app/static/kano-icon-192.png'});
  add('meta', {name: 'apple-mobile-web-app-capable', content: 'yes'});
  add('meta', {name: 'mobile-web-app-capable', content: 'yes'});
  add('meta', {name: 'apple-mobile-web-app-title', content: 'KANO'});
  add('meta', {name: 'application-name', content: 'KANO'});
  add('meta', {name: 'apple-mobile-web-app-status-bar-style', content: 'black'});
  add('meta', {name: 'theme-color', content: '#000000'});
  const vp = head.querySelector('meta[name="viewport"]');
  if (vp) vp.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');
})();
</script>
"""


def inject_head() -> None:
    st.html(_HEAD_JS, unsafe_allow_javascript=True)


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
