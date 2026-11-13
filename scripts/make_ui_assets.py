"""Generate small UI textures (stars, glow) into assets/ui. Run once: python scripts/make_ui_assets.py"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "assets" / "ui"
OUT.mkdir(parents=True, exist_ok=True)
S = 256


def star(points, inner, color, name, outline=None):
    im = Image.new("RGBA", (S * 2, S * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = S
    pts = []
    for i in range(points * 2):
        r = (S * 0.92) if i % 2 == 0 else (S * 0.92 * inner)
        a = -math.pi / 2 + i * math.pi / points
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=color, outline=outline)
    if outline:
        d.line(pts + [pts[0]], fill=outline, width=10, joint="curve")
    im.resize((S, S), Image.LANCZOS).save(OUT / name)


star(5, 0.45, (255, 205, 60, 255), "star_full.png")
star(5, 0.45, (20, 40, 90, 200), "star_empty.png", outline=(70, 110, 190, 255))
star(4, 0.25, (255, 255, 255, 255), "sparkle.png")

g = Image.new("RGBA", (S, S))
px = g.load()
for y in range(S):
    for x in range(S):
        d = math.hypot(x - S / 2, y - S / 2) / (S / 2)
        a = max(0.0, 1 - d) ** 2.2
        px[x, y] = (255, 255, 255, int(255 * a))
g.save(OUT / "glow.png")

# soft planet shading: dark crescent on one side for a 3D look
p = Image.new("RGBA", (S, S), (0, 0, 0, 0))
px = p.load()
for y in range(S):
    for x in range(S):
        dx, dy = (x - S / 2) / (S / 2), (y - S / 2) / (S / 2)
        if dx * dx + dy * dy <= 1:
            lit = max(0.0, min(1.0, 0.5 + (-dx * 0.55 - dy * 0.45) * 0.9))
            px[x, y] = (0, 0, 20, int(150 * (1 - lit)))
p.save(OUT / "planet_shade.png")

# seamless rocky ground texture (tile 3x3, blur, crop the centre so edges wrap)
import random
random.seed(3)
def octave(size, sigma, blur):
    n = Image.effect_noise((size * 3, size * 3), sigma).convert("L")
    return n.filter(ImageFilter.GaussianBlur(blur)).crop((size, size, size * 2, size * 2))
from PIL import ImageChops, ImageOps
base = octave(256, 60, 14)
fine = octave(256, 60, 3)
mix = Image.blend(base, fine, 0.35)
mix = ImageOps.autocontrast(mix, cutoff=2).point(lambda v: 150 + v * 0.42)
mix.convert("RGB").save(OUT / "ground.png")
print("assets written to", OUT)
