"""Mobiler Klick-Test mit Playwright inkl. Screenshots.

Voraussetzung: App läuft (streamlit run app.py) und `pip install playwright` (+ `playwright install chromium`).
Aufruf:  python scripts/mobile_check.py [URL] [ORDNER] [BREITE]
Beispiel: python scripts/mobile_check.py http://localhost:8501 screenshots 360

Ablauf: Konto registrieren → Onboarding → jede Hauptseite samt Tabs fotografieren →
neu laden (muss dank Cookie angemeldet bleiben) → prüfen, dass nichts horizontal überläuft.
"""

import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "screenshots")
WIDTH = int(sys.argv[3]) if len(sys.argv) > 3 else 390
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    "Heute": [],
    "Tracken": ["Suche", "Barcode", "Foto", "Favoriten"],
    "Plan": ["Einkauf", "Reste", "Schichten", "Preise"],
    "Fortschritt": ["Bedarf", "Woche", "Wohlbefinden", "Kraft"],
    "Coach": [],
    "Profil": ["Einstellungen", "Daten", "Konto"],
}


def settle(extra: float = 1.2) -> None:
    time.sleep(extra)


def shot(page: Page, name: str) -> None:
    settle()
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    flag = f"  ⚠ horizontaler Überlauf {overflow}px" if overflow > 2 else ""
    print(f"📸 {name}{flag}")


def goto(page: Page, url: str, selector: str) -> None:
    for attempt in range(4):  # Kaltstart des Servers kann dauern
        try:
            page.goto(url, timeout=60000)
            page.wait_for_selector(selector, timeout=30000)
            return
        except Exception:  # noqa: BLE001
            print("  … warte auf Server", attempt + 1)
    raise SystemExit(f"Seite {url} lädt nicht")


def main() -> None:
    email = f"test-{uuid.uuid4().hex[:6]}@kano.test"
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": WIDTH, "height": 800}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        goto(page, BASE, "text=Konto erstellen")
        shot(page, "01_login")

        page.get_by_role("tab", name="Konto erstellen").click()
        page.get_by_label("E-Mail").nth(1).fill(email)
        page.get_by_label("Passwort", exact=True).nth(1).fill("geheim1234")
        page.get_by_label("Passwort wiederholen").fill("geheim1234")
        page.get_by_role("button", name="Konto erstellen").click()
        page.wait_for_selector("text=Wichtig vorab", timeout=30000)
        shot(page, "02_onboarding_hinweise")
        page.get_by_text("Verstanden").click()
        for i, name in enumerate(["koerper", "ziel", "stil", "ergebnis"], start=3):
            page.get_by_role("button", name="Weiter", exact=True).click()
            settle(1.5)
            shot(page, f"0{i}_onboarding_{name}")
        page.get_by_role("button", name="Los geht's").click()
        page.wait_for_selector(".st-key-kano_nav", timeout=30000)

        for idx, (label, tabs) in enumerate(PAGES.items(), start=1):
            page.locator(f".st-key-kano_nav a:has-text('{label}')").first.click()
            settle(2)
            shot(page, f"{idx}0_{label.lower()}")
            for t_idx, tab in enumerate(tabs, start=1):
                page.get_by_role("tab", name=tab, exact=True).click()
                shot(page, f"{idx}{t_idx}_{label.lower()}_{tab.lower()}")

        goto(page, BASE, ".st-key-kano_nav")
        print("Angemeldet nach Neuladen:", page.locator(".st-key-kano_nav").count() > 0)
        body = page.inner_text("body")
        print("Fehlertext auf Seite:", "Traceback" in body)
        browser.close()
    print("JS-Fehler:", errors or "keine")
    print("Screenshots →", OUT.resolve())


if __name__ == "__main__":
    main()
