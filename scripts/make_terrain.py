"""Generate richer terrain art for the 3D worlds (does not touch any existing asset):

    python scripts/make_terrain.py

Writes into assets/ui/:
  ground_<mission>.png   1024px seamless rocky ground (pebbles, grain, cracks / plating) in each world's colours
  mottle_<mission>.png   large-scale light/dark patches laid over the ground to hide tiling
  rock.png               seamless grey rock texture used on boulders (tinted per world in game)
  crater.png             crater decal: bowl shading, bright lit rim and a soft cast shadow
  footprint.png          boot print decal
The old assets/ui/ground.png stays as the fallback.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

UI = Path(__file__).resolve().parent.parent / "assets" / "ui"
UI.mkdir(parents=True, exist_ok=True)

# base colours (match each mission's ground colour in missions.py) and character
WORLDS = {
    "moon": dict(base=(0.50, 0.50, 0.52), pebble=(0.72, 0.72, 0.74), dark=0.55, cracks=False, plating=False, grain=0.10),
    "mars": dict(base=(0.66, 0.36, 0.22), pebble=(0.82, 0.5, 0.33), dark=0.5, cracks=True, plating=False, grain=0.12),
    "orbital": dict(base=(0.72, 0.74, 0.8), pebble=(0.9, 0.92, 0.96), dark=0.6, cracks=False, plating=True, grain=0.05),
    "europa": dict(base=(0.78, 0.84, 0.92), pebble=(0.95, 0.98, 1.0), dark=0.62, cracks=True, plating=False, grain=0.06),
}


def fbm2(n, octaves=6, base=4, persistence=0.55, seed=0):
    """Seamless (both axes) fractal noise in [0,1], n x n."""
    rng = np.random.default_rng(seed)
    out = np.zeros((n, n), np.float32)
    amp = tot = 1.0
    out[:] = 0
    tot = 0.0
    amp = 1.0
    for o in range(octaves):
        g = base * 2 ** o
        grid = rng.random((g, g)).astype(np.float32)
        big = np.tile(grid, (3, 3))
        im = Image.fromarray(big).resize((n * 3, n * 3), Image.BICUBIC)
        a = np.asarray(im, np.float32)[n:2 * n, n:2 * n]
        out += a * amp
        tot += amp
        amp *= persistence
    out /= tot
    out -= out.min()
    return out / max(1e-6, out.max())


def wrap_draw(draw_fn, n, x, y, r):
    """Call draw_fn(cx, cy) for the centre and any wrapped copies so seams stay invisible."""
    for dx in (-n, 0, n):
        for dy in (-n, 0, n):
            cx, cy = x + dx, y + dy
            if -r <= cx <= n + r and -r <= cy <= n + r:
                draw_fn(cx, cy)


def make_ground(name, cfg, n=1024, seed=0):
    rng = np.random.default_rng(seed + 11)
    base = np.array(cfg["base"], np.float32)
    big = fbm2(n, 5, 3, 0.6, seed + 1)
    mid = fbm2(n, 6, 10, 0.55, seed + 2)
    fine = fbm2(n, 4, 64, 0.5, seed + 3)
    lum = 0.62 + 0.5 * (big - 0.5) + 0.5 * (mid - 0.5) + cfg["grain"] * 1.6 * (fine - 0.5) * 2
    img = np.clip(lum[..., None] * base[None, None, :] * 1.15, 0, 1)
    # slightly warm/cool mottling so it never looks flat
    tint = (fbm2(n, 4, 5, 0.6, seed + 4) - 0.5)[..., None] * np.array([0.05, 0.02, -0.04], np.float32)
    img = np.clip(img + tint, 0, 1)
    im = Image.fromarray((img * 255).astype(np.uint8)).convert("RGBA")

    over = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    lit = tuple(int(c * 255) for c in cfg["pebble"])
    shade = tuple(int(c * 255 * cfg["dark"]) for c in cfg["base"])
    # pebbles / small rocks: shadow offset down-right, lit body, highlight up-left
    for _ in range(900):
        x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
        r = float(rng.choice([3, 4, 6, 9, 13, 19, 28, 40], p=[0.2, 0.2, 0.18, 0.15, 0.1, 0.08, 0.06, 0.03]))
        rx, ry = r * rng.uniform(0.8, 1.35), r * rng.uniform(0.7, 1.1)
        k = rng.uniform(0.75, 1.0)
        body = tuple(int(c * k) for c in lit)

        def pebble(cx, cy, rx=rx, ry=ry, body=body):
            d.ellipse([cx - rx + 2, cy - ry + 3, cx + rx + 3, cy + ry + 4], fill=shade + (150,))
            d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=body + (235,))
            d.ellipse([cx - rx * 0.6, cy - ry * 0.7, cx + rx * 0.1, cy + ry * 0.1],
                      fill=tuple(min(255, int(c * 1.15)) for c in body) + (130,))
        wrap_draw(pebble, n, x, y, rx + 6)
    # small impact pits
    for _ in range(26):
        x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
        r = float(rng.uniform(24, 70))

        def pit(cx, cy, r=r):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade + (70,))
            d.ellipse([cx - r * 0.8 + 3, cy - r * 0.8 + 4, cx + r * 0.8 + 3, cy + r * 0.8 + 4], fill=shade + (50,))
            d.arc([cx - r, cy - r, cx + r, cy + r], 200, 300, fill=lit + (150,), width=2)
        wrap_draw(pit, n, x, y, r + 4)
    if cfg["cracks"]:                                    # dried-mud / ice cracks: random walks
        for _ in range(26):
            x, y = float(rng.integers(0, n)), float(rng.integers(0, n))
            ang = rng.uniform(0, 6.28)
            pts = [(x, y)]
            for _s in range(int(rng.integers(12, 40))):
                ang += rng.normal(0, 0.45)
                x += math.cos(ang) * rng.uniform(8, 22)
                y += math.sin(ang) * rng.uniform(8, 22)
                pts.append((x, y))
            for dx in (-n, 0, n):
                for dy in (-n, 0, n):
                    d.line([(px + dx, py + dy) for px, py in pts], fill=shade + (190,), width=int(rng.integers(2, 4)))
                    d.line([(px + dx + 2, py + dy + 2) for px, py in pts], fill=lit + (70,), width=1)
    if cfg["plating"]:                                   # orbital: hull plating with seams and rivets
        step = n // 4
        for i in range(0, n + 1, step):
            d.line([(i, 0), (i, n)], fill=(20, 24, 34, 230), width=5)
            d.line([(0, i), (n, i)], fill=(20, 24, 34, 230), width=5)
            d.line([(i + 4, 0), (i + 4, n)], fill=(230, 235, 245, 90), width=2)
            d.line([(0, i + 4), (n, i + 4)], fill=(230, 235, 245, 90), width=2)
        for px in range(step // 2, n, step):
            for py in range(step // 2, n, step):
                for ox, oy in ((-90, -90), (90, -90), (-90, 90), (90, 90)):
                    d.ellipse([px + ox - 6, py + oy - 6, px + ox + 6, py + oy + 6], fill=(40, 46, 60, 255))
                    d.ellipse([px + ox - 3, py + oy - 4, px + ox + 2, py + oy + 1], fill=(220, 228, 240, 220))
        for _ in range(60):                              # scratches
            x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
            d.line([(x, y), (x + int(rng.integers(-60, 60)), y + int(rng.integers(-60, 60)))], fill=(235, 240, 250, 60), width=1)
    over = over.filter(ImageFilter.GaussianBlur(0.7))
    im = Image.alpha_composite(im, over)
    im.convert("RGB").save(UI / f"ground_{name}.png")


def make_detail(name, cfg, n=1024, seed=0):
    """Crisp close-range detail (pebbles and grain on a transparent layer) tiled every ~3 units over the ground."""
    rng = np.random.default_rng(seed + 55)
    fine = fbm2(n, 5, 48, 0.55, seed + 56)
    speck = np.zeros((n, n, 4), np.float32)
    dark = np.clip((0.42 - fine) * 3.2, 0, 1)
    light = np.clip((fine - 0.62) * 3.2, 0, 1)
    speck[..., :3] = np.array([0.03, 0.03, 0.04], np.float32)
    speck[..., 3] = dark * 0.35
    lt = np.zeros((n, n, 4), np.float32)
    lt[..., :3] = np.clip(np.array(cfg["pebble"], np.float32) * 1.05, 0, 1)
    lt[..., 3] = light * 0.3
    base = Image.alpha_composite(Image.fromarray((speck * 255).astype(np.uint8), "RGBA"),
                                 Image.fromarray((lt * 255).astype(np.uint8), "RGBA"))
    over = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    lit = tuple(int(c * 255) for c in cfg["pebble"])
    shade = tuple(int(c * 255 * cfg["dark"] * 0.6) for c in cfg["base"])
    for _ in range(130):
        x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
        r = float(rng.choice([7, 10, 14, 20, 28, 40], p=[0.28, 0.25, 0.2, 0.15, 0.08, 0.04]))
        rx, ry = r * rng.uniform(0.85, 1.4), r * rng.uniform(0.7, 1.05)
        k = rng.uniform(0.7, 1.0)
        body = tuple(int(c * k) for c in lit)

        def pebble(cx, cy, rx=rx, ry=ry, body=body):
            d.ellipse([cx - rx + 5, cy - ry + 7, cx + rx + 8, cy + ry + 9], fill=shade + (120,))
            d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=body + (255,))
            d.ellipse([cx - rx * 0.65, cy - ry * 0.75, cx + rx * 0.05, cy + ry * 0.05], fill=tuple(min(255, int(c * 1.18)) for c in body) + (150,))
            d.arc([cx - rx, cy - ry, cx + rx, cy + ry], 20, 110, fill=shade + (170,), width=2)
        wrap_draw(pebble, n, x, y, rx + 10)
    over = over.filter(ImageFilter.GaussianBlur(1.0))
    Image.alpha_composite(base, over).save(UI / f"detail_{name}.png")


def make_mottle(name, cfg, n=512, seed=0):
    """Large soft patches (non-tiling, covers the whole 140-unit plane) to break up the repeating tile."""
    a = fbm2(n, 5, 3, 0.6, seed + 30)
    b = fbm2(n, 4, 8, 0.5, seed + 31)
    v = 0.6 * a + 0.4 * b
    dark = np.clip((0.5 - v) * 3.0, 0, 1)
    light = np.clip((v - 0.55) * 3.0, 0, 1)
    out = np.zeros((n, n, 4), np.float32)
    out[..., :3] = np.array([0.02, 0.02, 0.03], np.float32)
    out[..., 3] = dark * 0.32
    lt = np.zeros((n, n, 4), np.float32)
    lt[..., :3] = np.clip(np.array(cfg["pebble"], np.float32) * 1.1, 0, 1)
    lt[..., 3] = light * 0.12
    A = Image.fromarray((out * 255).astype(np.uint8), "RGBA")
    B = Image.fromarray((lt * 255).astype(np.uint8), "RGBA")
    Image.alpha_composite(A, B).resize((1024, 1024), Image.BICUBIC).save(UI / f"mottle_{name}.png")


def make_rock(n=256):
    big = fbm2(n, 5, 4, 0.6, 71)
    mid = fbm2(n, 5, 16, 0.55, 72)
    v = 0.6 + 0.55 * (big - 0.5) + 0.35 * (mid - 0.5)
    ridges = np.abs(fbm2(n, 4, 8, 0.5, 73) - 0.5) * 2
    v = v - 0.18 * (1 - ridges) ** 4
    img = np.clip(np.stack([v * 1.0, v * 0.98, v * 0.96], -1), 0, 1)
    Image.fromarray((img * 255).astype(np.uint8)).save(UI / "rock.png")


def make_crater(n=512):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    cx = cy = n / 2
    r = np.hypot(xx - cx, yy - cy) / (n / 2)
    ang = np.arctan2(yy - cy, xx - cx)
    light = np.cos(ang + 2.3)                                  # light from the upper left
    noise = fbm2(n, 5, 6, 0.6, 90)
    wob = 1 + 0.06 * (noise - 0.5)
    rr = r * wob
    bowl = np.clip(1 - rr / 0.62, 0, 1)
    rim = np.exp(-((rr - 0.66) ** 2) / 0.0035)
    outer = np.exp(-np.clip(rr - 0.7, 0, None) / 0.07) * (rr > 0.7)
    a = np.zeros((n, n, 4), np.float32)
    shadow = np.clip(0.35 + 0.5 * (-light) * np.clip(rr / 0.62, 0, 1), 0, 1) * (rr < 0.66)
    a[..., :3] = 0.04
    a[..., 3] = (bowl ** 0.6 * 0.2 + shadow * 0.34) * (rr < 0.66)
    hi = rim * np.clip(0.4 + 0.9 * light, 0, 1)
    a[..., :3] = np.where(hi[..., None] > 0.05, np.array([0.78, 0.76, 0.74]), a[..., :3])
    a[..., 3] = np.maximum(a[..., 3], hi * 0.38)
    a[..., 3] = np.maximum(a[..., 3], outer * 0.18 * (0.5 + 0.5 * (-light)))   # soft cast shadow outside the rim
    a[..., 3] *= (rr < 1.0) * np.clip((1.0 - rr) / 0.08, 0, 1)
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGBA").save(UI / "crater.png")


def make_footprint():
    im = Image.new("RGBA", (64, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([14, 62, 50, 120], radius=14, fill=(0, 0, 0, 150))        # heel
    d.rounded_rectangle([10, 8, 54, 62], radius=18, fill=(0, 0, 0, 150))          # sole
    for y in range(14, 118, 9):                                                    # tread
        d.line([(16, y), (48, y)], fill=(255, 255, 255, 45), width=2)
    im.filter(ImageFilter.GaussianBlur(1.1)).save(UI / "footprint.png")


def make_blob_shadow(n=128):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    r = np.hypot(xx - n / 2, yy - n / 2) / (n / 2)
    a = np.clip(1 - r, 0, 1) ** 1.6
    out = np.zeros((n, n, 4), np.uint8)
    out[..., 3] = (a * 255).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(UI / "blob_shadow.png")


if __name__ == "__main__":
    for i, (name, cfg) in enumerate(WORLDS.items()):
        make_ground(name, cfg, seed=i * 7)
        make_mottle(name, cfg, seed=i * 7)
        make_detail(name, cfg, seed=i * 7)
    make_rock()
    make_crater()
    make_footprint()
    make_blob_shadow()
    print("terrain art written to", UI)
