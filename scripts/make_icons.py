"""Erzeugt das App-Icon (Gradient-„K“ auf Schwarz) in allen benötigten Größen.

Aufruf:  python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
STOPS = [(0.0, (0x28, 0x70, 0xEA)), (0.35, (0x7B, 0x61, 0xFF)), (0.7, (0xE3, 0x00, 0x8C)), (1.0, (0xFF, 0x8C, 0x00))]
S = 2048  # Arbeitsauflösung (danach herunterskaliert → glatte Kanten)


def lerp_color(t: float) -> tuple[int, int, int]:
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
    return STOPS[-1][1]


def gradient(size: int) -> Image.Image:
    """Diagonaler Verlauf von links oben nach rechts unten."""
    small = 256
    img = Image.new("RGB", (small, small))
    px = img.load()
    for y in range(small):
        for x in range(small):
            t = ((x + y) / (2 * (small - 1)) - 0.22) / 0.56  # Verlauf über die Fläche des K
            px[x, y] = lerp_color(max(0.0, min(1.0, t)))
    return img.resize((size, size), Image.BICUBIC)


def k_mask(size: int) -> Image.Image:
    """Geometrisches „K“: Stamm + zwei Arme mit abgerundeten Enden."""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    u = size / 100
    stroke = 13 * u
    top, bottom = 24 * u, 76 * u
    stem_x = 33 * u
    d.rounded_rectangle([stem_x - stroke / 2, top, stem_x + stroke / 2, bottom], radius=stroke / 2, fill=255)
    join = (stem_x + stroke * 0.35, 52 * u)
    d.line([join, (68 * u, top + stroke / 2)], fill=255, width=int(stroke))
    d.line([(join[0] + 3 * u, 50 * u), (69 * u, bottom - stroke / 2)], fill=255, width=int(stroke))
    for cx, cy in [(68 * u, top + stroke / 2), (69 * u, bottom - stroke / 2)]:
        d.ellipse([cx - stroke / 2, cy - stroke / 2, cx + stroke / 2, cy + stroke / 2], fill=255)
    return m


def main() -> None:
    base = Image.new("RGB", (S, S), (0, 0, 0))
    mask = k_mask(S)
    grad = gradient(S)
    # dezenter Schein hinter dem K
    glow = Image.composite(grad, base, mask.filter(ImageFilter.GaussianBlur(S / 30)).point(lambda v: int(v * 0.35)))
    icon = Image.composite(grad, glow, mask)
    out = ROOT / "static"
    out.mkdir(exist_ok=True)
    for size in (512, 192, 180, 32):
        icon.resize((size, size), Image.LANCZOS).save(out / f"kano-icon-{size}.png", optimize=True)
    print("Icons geschrieben nach", out)


if __name__ == "__main__":
    main()
