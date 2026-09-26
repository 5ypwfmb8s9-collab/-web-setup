"""Barcodes (EAN-13/EAN-8/UPC) aus Fotos lesen – mit zxing-cpp, ohne Systembibliotheken."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

try:
    import zxingcpp
except ImportError:  # pragma: no cover - optional
    zxingcpp = None


def valid_ean(code: str) -> bool:
    """Prüfziffer für EAN-8/EAN-13/UPC-A (12) prüfen."""
    if not code.isdigit() or len(code) not in (8, 12, 13):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    # Gewichte von rechts: 3,1,3,1 …
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def decode(image_bytes: bytes) -> str | None:
    """Erster gültiger Produkt-Barcode im Bild oder None."""
    if zxingcpp is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("L")
    except Exception:
        return None
    # Große Handyfotos verkleinern (schneller, oft sogar zuverlässiger)
    img.thumbnail((1600, 1600))
    for candidate in (img, ImageOps.autocontrast(img)):
        for result in zxingcpp.read_barcodes(candidate):
            text = (result.text or "").strip()
            if valid_ean(text):
                return text
    return None
