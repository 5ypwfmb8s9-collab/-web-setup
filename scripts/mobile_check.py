"""Mobiler Klick-Test mit Playwright (iPhone-Viewport) inkl. Screenshots.

Voraussetzung: App läuft (streamlit run app.py) und `pip install playwright`.
Aufruf:  python scripts/mobile_check.py http://localhost:8501 ./screenshots
Legt ein Testkonto an, durchläuft das Onboarding und fotografiert alle Hauptseiten.
"""

import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "screenshots")
OUT.mkdir(parents=True, exist_ok=True)


def settle(page: Page, extra: float = 0.6) -> None:
    """Wartet, bis Streamlit fertig gerechnet hat."""
    time.sleep(0.4)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')?.innerText?.includes('Running')",
        timeout=30000,
    )
    time.sleep(extra)


def shot(page: Page, name: str, full: bool = True) -> None:
    settle(page)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("📸", name)


def click_button(page: Page, text: str) -> None:
    page.get_by_role("button", name=text, exact=True).first.click()
    settle(page)


def main() -> None:
    email = f"test-{uuid.uuid4().hex[:6]}@kano.test"
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE)
        page.wait_for_selector("text=Konto erstellen", timeout=30000)
        shot(page, "01_login")

        page.get_by_role("tab", name="Konto erstellen").click()
        page.get_by_label("E-Mail").nth(1).fill(email)
        page.get_by_label("Passwort", exact=True).nth(1).fill("geheim1234")
        page.get_by_label("Passwort wiederholen").fill("geheim1234")
        click_button(page, "Konto erstellen")
        page.wait_for_selector("text=Willkommen", timeout=20000)
        shot(page, "02_onboarding_1")
        page.get_by_text("Verstanden").click()
        click_button(page, "Weiter")
        shot(page, "03_onboarding_2")
        click_button(page, "Weiter")
        shot(page, "04_onboarding_3")
        click_button(page, "Weiter")
        shot(page, "05_onboarding_4")
        click_button(page, "Weiter")
        shot(page, "06_onboarding_5")
        click_button(page, "Los geht's")
        page.wait_for_selector(".st-key-kano_nav", timeout=20000)
        shot(page, "10_heute", full=False)

        for key, label in [("tracken", "Tracken"), ("plan", "Plan"), ("fortschritt", "Fortschritt"), ("coach", "Coach"), ("profil", "Profil")]:
            page.locator(f".st-key-kano_nav a:has-text('{label}')").first.click()
            settle(page, 1.0)
            shot(page, f"2{list('tpfcx').index(key[0]) if key[0] in 'tpfcx' else 9}_{key}", full=False)

        # Neu laden → muss dank Cookie angemeldet bleiben
        page.goto(BASE)
        settle(page, 1.5)
        still_in = page.locator(".st-key-kano_nav").count() > 0
        print("Angemeldet nach Reload:", still_in)
        browser.close()
    if errors:
        print("JS-Fehler:", *errors, sep="\n  ")
    print("fertig →", OUT)


if __name__ == "__main__":
    main()
