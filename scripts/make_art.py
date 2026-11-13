"""Generate all procedural art for Astro Play (nebulae, star layers, planet horizon, sky domes,
planet textures, icons, effect sprites).  Run once:  python scripts/make_art.py
Everything is drawn from scratch, so there are no licensing worries."""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "assets" / "ui"
SKY = ROOT / "assets" / "sky"
UI.mkdir(parents=True, exist_ok=True)
SKY.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------- noise helpers
def fbm(w, h, octaves=6, base=3, persistence=0.55, seed=0, tile_x=True):
    """Fractal value noise in [0,1]; seamless horizontally when tile_x is True."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gw = base * 2 ** o
        gh = max(2, int(round(gw * h / w)))
        g = rng.random((gh + 1, gw)).astype(np.float32)
        g3 = np.tile(g, (1, 3))
        im = Image.fromarray(g3).resize((w * 3, h), Image.BICUBIC)
        a = np.asarray(im, np.float32)[:, w:2 * w] if tile_x else np.asarray(im, np.float32)[:, :w]
        out += a * amp
        total += amp
        amp *= persistence
    out /= total
    out -= out.min()
    return out / max(1e-6, out.max())


def to_img(rgba):
    return Image.fromarray(np.clip(rgba * 255, 0, 255).astype(np.uint8), "RGBA")


def smooth(a, lo, hi):
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def starfield(w, h, count, size_range, seed, tint=True, bright=(0.55, 1.0)):
    """RGBA star layer (transparent background)."""
    rng = np.random.default_rng(seed)
    canvas = np.zeros((h, w, 4), np.float32)
    for _ in range(count):
        x, y = int(rng.integers(16, w - 16)), int(rng.integers(16, h - 16))
        r = rng.uniform(*size_range)
        b = rng.uniform(*bright)
        c = np.array([1, 1, 1], np.float32)
        if tint:
            c = rng.choice([0, 1, 2], p=[0.6, 0.2, 0.2])
            c = [np.array([0.95, 0.97, 1.0]), np.array([0.7, 0.85, 1.0]), np.array([1.0, 0.88, 0.7])][c]
        k = int(math.ceil(r * 3))
        yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
        g = np.exp(-(xx * xx + yy * yy) / (2 * (r * 0.55) ** 2)) * b
        ys, xs = slice(y - k, y + k + 1), slice(x - k, x + k + 1)
        canvas[ys, xs, :3] = np.maximum(canvas[ys, xs, :3], g[..., None] * c)
        canvas[ys, xs, 3] = np.maximum(canvas[ys, xs, 3], g)
        if r > 2.2:  # little cross flare on bright stars
            for d in range(1, int(r * 4)):
                f = b * (1 - d / (r * 4)) ** 2 * 0.7
                for (dx, dy) in ((d, 0), (-d, 0), (0, d), (0, -d)):
                    xx2, yy2 = x + dx, y + dy
                    if 0 <= xx2 < w and 0 <= yy2 < h:
                        canvas[yy2, xx2, :3] = np.maximum(canvas[yy2, xx2, :3], c * f)
                        canvas[yy2, xx2, 3] = max(canvas[yy2, xx2, 3], f)
    return to_img(canvas)


# ----------------------------------------------------------------------------- backgrounds
def make_nebulae():
    w, h = 960, 540
    n1, n2, n3 = fbm(w, h, 6, 3, 0.55, 1), fbm(w, h, 6, 4, 0.5, 2), fbm(w, h, 5, 2, 0.6, 3)
    # purple / magenta cloud
    a = smooth(n1, 0.38, 0.85) ** 1.4
    col = np.zeros((h, w, 4), np.float32)
    col[..., 0] = 0.55 + 0.35 * n2
    col[..., 1] = 0.18 + 0.10 * n3
    col[..., 2] = 0.95
    col[..., 3] = a * 0.85
    big = Image.new("RGBA", (1920, 1080))
    to_img(col).resize((1920, 1080), Image.BICUBIC).save(UI / "nebula_a.png")
    # cyan / blue cloud
    a = smooth(n2, 0.42, 0.88) ** 1.5
    col = np.zeros((h, w, 4), np.float32)
    col[..., 0] = 0.10
    col[..., 1] = 0.55 + 0.35 * n3
    col[..., 2] = 1.0
    col[..., 3] = a * 0.7
    to_img(col).resize((1920, 1080), Image.BICUBIC).save(UI / "nebula_b.png")
    for i, (cnt, sz, seed, br) in enumerate(((900, (0.7, 1.4), 11, (0.35, 0.8)),
                                            (320, (1.3, 2.2), 12, (0.55, 0.95)),
                                            (70, (2.2, 3.4), 13, (0.8, 1.0)))):
        starfield(1920, 1080, cnt, sz, seed, bright=br).save(UI / f"stars_{i}.png")


def make_horizon():
    """Limb of a huge planet with a glowing atmosphere, drawn along the bottom of screens."""
    w, h = 1920, 640
    cx, cy, R = w / 2, h + 1900, 2300
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot(xx - cx, yy - cy)
    surface = d < R
    rim = np.clip((d - (R - 90)) / 90, 0, 1)              # 0 inside .. 1 at the edge
    glow = np.exp(-np.clip(d - R, 0, None) / 60.0)         # atmosphere outside
    n = fbm(w, h, 6, 5, 0.55, 21)
    band = 0.5 + 0.5 * np.sin((yy - cy) / 9.0 + n * 5)
    base = np.zeros((h, w, 4), np.float32)
    base[..., 0] = 0.02 + 0.05 * band
    base[..., 1] = 0.06 + 0.10 * band
    base[..., 2] = 0.20 + 0.22 * band + 0.1 * n
    base[..., 3] = surface * 0.96
    # lit rim (cyan -> violet toward the sides)
    side = np.clip(np.abs(xx - cx) / (w / 2), 0, 1)
    rc = np.array([0.15, 0.85, 1.0]) * (1 - side[..., None]) + np.array([0.6, 0.35, 1.0]) * side[..., None]
    base[..., :3] = base[..., :3] * (1 - rim[..., None] ** 2 * 0.8) + rc * (rim[..., None] ** 3) * 0.95
    out = base.copy()
    outside = ~surface
    out[outside, :3] = rc[outside] * 0.9
    out[outside, 3] = (glow[outside] ** 1.4) * 0.8
    img = to_img(out).filter(ImageFilter.GaussianBlur(0.8))
    img.save(UI / "horizon.png")


def make_effect_sprites():
    S = 256
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    d = np.hypot(xx - S / 2, yy - S / 2) / (S / 2)
    # thin glowing ring used for scan / hit pulses
    ring = np.exp(-((d - 0.82) ** 2) / 0.0016) + 0.35 * np.exp(-((d - 0.82) ** 2) / 0.02)
    img = np.zeros((S, S, 4), np.float32)
    img[..., :3] = 1
    img[..., 3] = np.clip(ring, 0, 1) * (d < 1)
    to_img(img).save(UI / "pulse_ring.png")
    # soft vignette
    w, h = 640, 360
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dd = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    v = np.zeros((h, w, 4), np.float32)
    v[..., 2] = 0.04
    v[..., 3] = np.clip((dd - 0.55) / 0.85, 0, 1) ** 1.6 * 0.75
    to_img(v).resize((1920, 1080), Image.BICUBIC).save(UI / "vignette.png")
    # vertical light beam (fades at the top)
    bw, bh = 64, 256
    yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
    prof = np.exp(-((xx - bw / 2) / (bw * 0.22)) ** 2)
    fade = (yy / bh) ** 1.6
    b = np.zeros((bh, bw, 4), np.float32)
    b[..., :3] = 1
    b[..., 3] = prof * fade
    to_img(b).save(UI / "beam.png")
    # round dust speck
    g = np.zeros((64, 64, 4), np.float32)
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    g[..., :3] = 1
    g[..., 3] = np.clip(1 - np.hypot(xx - 32, yy - 32) / 32, 0, 1) ** 2
    to_img(g).save(UI / "speck.png")


# ----------------------------------------------------------------------------- sky domes & planets
def make_sky(name, zenith, horizon, star_count, seed, nebula=None, glow_at=None):
    w, h = 2048, 1024
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None]            # 0 top .. 1 bottom
    k = np.clip(1 - np.abs(t - 0.5) * 2, 0, 1)                      # 1 at horizon (middle of equirect)
    z, hz = np.array(zenith, np.float32), np.array(horizon, np.float32)
    img = np.zeros((h, w, 4), np.float32)
    mix = k ** 1.7
    img[..., :3] = z * (1 - mix[..., None]) + hz * mix[..., None]
    img[..., 3] = 1
    if nebula is not None:                                          # faint milky-way band
        n = fbm(w, h, 6, 3, 0.55, seed + 5)
        band = np.exp(-((t - 0.34) / 0.12) ** 2)
        m = smooth(n, 0.4, 0.9) * band * nebula[3]
        for c in range(3):
            img[..., c] += m * nebula[c]
    st = starfield(w, h, star_count, (0.7, 1.6), seed, bright=(0.4, 1.0))
    st2 = starfield(w, h, star_count // 8, (1.6, 2.8), seed + 1, bright=(0.7, 1.0))
    base = to_img(img)
    base = Image.alpha_composite(base, st)
    base = Image.alpha_composite(base, st2)
    base.convert("RGB").save(SKY / f"{name}.png")


def make_planet_textures():
    w, h = 1024, 512
    # Earth: ocean + continents + clouds
    land = fbm(w, h, 7, 3, 0.55, 40)
    clouds = fbm(w, h, 7, 4, 0.6, 41)
    yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    ocean = np.zeros((h, w, 3), np.float32)
    ocean[...] = (0.02, 0.18, 0.55)
    ocean += (0.0, 0.12, 0.2) * smooth(land, 0.30, 0.48)[..., None]
    land_mask = smooth(land, 0.52, 0.55)
    green = np.array([0.18, 0.55, 0.22], np.float32)
    sand = np.array([0.72, 0.62, 0.38], np.float32)
    lc = green * (1 - smooth(land, 0.62, 0.8)[..., None]) + sand * smooth(land, 0.62, 0.8)[..., None]
    col = ocean * (1 - land_mask[..., None]) + lc * land_mask[..., None]
    ice = smooth(np.abs(yy), 0.82, 0.95) * np.ones((1, w), np.float32)
    col = col * (1 - ice[..., None]) + np.array([0.92, 0.96, 1.0]) * ice[..., None]
    cl = smooth(clouds, 0.5, 0.78) * 0.85
    col = col * (1 - cl[..., None]) + cl[..., None]
    Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8), "RGB").save(SKY / "earth.png")
    # Jupiter: banded gas giant with a storm
    n = fbm(w, h, 6, 4, 0.55, 50)
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    bands = 0.5 + 0.5 * np.sin(y * 34 + n * 3.2 + np.sin(y * 9) * 1.5)
    pal_a, pal_b = np.array([0.86, 0.62, 0.42]), np.array([0.98, 0.9, 0.78])
    col = pal_a * (1 - bands[..., None]) + pal_b * bands[..., None]
    col *= (0.85 + 0.3 * n[..., None])
    sx, sy = int(w * 0.62), int(h * 0.62)
    yy2, xx2 = np.mgrid[0:h, 0:w].astype(np.float32)
    spot = np.exp(-(((xx2 - sx) / 70) ** 2 + ((yy2 - sy) / 36) ** 2))
    col = col * (1 - spot[..., None] * 0.9) + np.array([0.78, 0.27, 0.15]) * spot[..., None] * 0.9
    Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8), "RGB").save(SKY / "jupiter.png")
    # simple sun disc glow (billboard)
    S = 512
    yy3, xx3 = np.mgrid[0:S, 0:S].astype(np.float32)
    d = np.hypot(xx3 - S / 2, yy3 - S / 2) / (S / 2)
    a = np.clip(1 - d, 0, 1) ** 2.4 + (d < 0.18) * 1.0
    sun = np.zeros((S, S, 4), np.float32)
    sun[..., 0], sun[..., 1], sun[..., 2] = 1, 0.93, 0.75
    sun[..., 3] = np.clip(a, 0, 1)
    to_img(sun).save(SKY / "sun.png")


# ----------------------------------------------------------------------------- icons
SS = 4                   # supersampling
N = 128 * SS


def canvas():
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def save_icon(im, name):
    im.resize((128, 128), Image.LANCZOS).save(UI / f"{name}.png")


def P(v):  # 0..512 design grid -> pixels
    return v * N / 512


def icon_note(off=False):
    im, d = canvas()
    a = 255 if not off else 120
    wc = (255, 255, 255, a)
    d.ellipse([P(95), P(340), P(205), P(420)], fill=wc)
    d.ellipse([P(285), P(305), P(395), P(385)], fill=wc)
    d.rectangle([P(186), P(150), P(210), P(380)], fill=wc)
    d.rectangle([P(376), P(115), P(400), P(345)], fill=wc)
    d.polygon([(P(186), P(150)), (P(400), P(112)), (P(400), P(172)), (P(186), P(212))], fill=wc)
    if off:
        d.line([(P(70), P(90)), (P(445), P(445))], fill=(255, 90, 105, 255), width=int(P(44)))
    save_icon(im, "icon_music_off" if off else "icon_music_on")


def icon_speaker(off=False):
    im, d = canvas()
    a = 255 if not off else 120
    wc = (255, 255, 255, a)
    d.rectangle([P(80), P(190), P(170), P(322)], fill=wc)
    d.polygon([(P(160), P(190)), (P(270), P(105)), (P(270), P(407)), (P(160), P(322))], fill=wc)
    if not off:
        d.arc([P(240), P(170), P(360), P(342)], -55, 55, fill=wc, width=int(P(28)))
        d.arc([P(240), P(110), P(430), P(402)], -55, 55, fill=wc, width=int(P(28)))
    else:
        d.line([(P(70), P(90)), (P(445), P(445))], fill=(255, 90, 105, 255), width=int(P(44)))
    save_icon(im, "icon_sfx_off" if off else "icon_sfx_on")


def icon_globe():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    w = int(P(26))
    d.ellipse([P(80), P(80), P(432), P(432)], outline=wc, width=w)
    d.ellipse([P(170), P(80), P(342), P(432)], outline=wc, width=int(P(22)))
    d.line([(P(256), P(80)), (P(256), P(432))], fill=wc, width=int(P(20)))
    d.line([(P(80), P(256)), (P(432), P(256))], fill=wc, width=int(P(20)))
    d.arc([P(80), P(150), P(432), P(362)], 0, 180, fill=wc, width=int(P(16)))
    d.arc([P(80), P(150), P(432), P(362)], 180, 360, fill=wc, width=int(P(16)))
    save_icon(im, "icon_globe")


def icon_scan():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.ellipse([P(70), P(70), P(442), P(442)], outline=wc, width=int(P(26)))
    d.ellipse([P(150), P(150), P(362), P(362)], outline=(255, 255, 255, 170), width=int(P(16)))
    d.ellipse([P(226), P(226), P(286), P(286)], fill=wc)
    for (x1, y1, x2, y2) in ((256, 20, 256, 110), (256, 402, 256, 492), (20, 256, 110, 256), (402, 256, 492, 256)):
        d.line([(P(x1), P(y1)), (P(x2), P(y2))], fill=wc, width=int(P(22)))
    d.pieslice([P(70), P(70), P(442), P(442)], -60, -20, fill=(255, 255, 255, 110))
    save_icon(im, "icon_scan")


def icon_collect():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.rounded_rectangle([P(180), P(110), P(332), P(430)], radius=int(P(60)), outline=wc, width=int(P(26)))
    d.rounded_rectangle([P(160), P(70), P(352), P(125)], radius=int(P(20)), fill=wc)
    d.rounded_rectangle([P(194), P(270), P(318), P(416)], radius=int(P(48)), fill=(255, 255, 255, 200))
    d.ellipse([P(222), P(205), P(250), P(233)], fill=(255, 255, 255, 190))
    d.ellipse([P(266), P(170), P(286), P(190)], fill=(255, 255, 255, 150))
    save_icon(im, "icon_collect")


def icon_analyze():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    heights = (170, 300, 220, 380, 250)
    for i, hh in enumerate(heights):
        x = 70 + i * 74
        d.rounded_rectangle([P(x), P(440 - hh), P(x + 48), P(440)], radius=int(P(22)), fill=wc)
    d.line([(P(50), P(455)), (P(462), P(455))], fill=(255, 255, 255, 170), width=int(P(14)))
    save_icon(im, "icon_analyze")


def icon_repair():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.line([(P(120), P(410)), (P(300), P(230))], fill=wc, width=int(P(70)))
    d.ellipse([P(85), P(375), P(155), P(445)], fill=wc)
    d.ellipse([P(255), P(60), P(465), P(270)], fill=wc)
    d.polygon([(P(360), P(165)), (P(500), P(40)), (P(520), P(150)), (P(420), P(230))], fill=(0, 0, 0, 0))
    save_icon(im, "icon_repair")


def icon_lock():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.rounded_rectangle([P(110), P(230), P(402), P(440)], radius=int(P(36)), fill=wc)
    d.arc([P(170), P(80), P(342), P(330)], 180, 360, fill=wc, width=int(P(36)))
    d.rectangle([P(170), P(190), P(206), P(250)], fill=wc)
    d.rectangle([P(306), P(190), P(342), P(250)], fill=wc)
    d.ellipse([P(232), P(305), P(280), P(353)], fill=(0, 0, 0, 0))
    save_icon(im, "icon_lock")


def icon_check():
    im, d = canvas()
    d.line([(P(95), P(270)), (P(210), P(380)), (P(425), P(135))], fill=(255, 255, 255, 255), width=int(P(60)), joint="curve")
    save_icon(im, "icon_check")


def icon_hint():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.ellipse([P(120), P(50), P(392), P(322)], fill=wc)
    d.polygon([(P(190), P(290)), (P(322), P(290)), (P(300), P(370)), (P(212), P(370))], fill=wc)
    d.rounded_rectangle([P(205), P(385), P(307), P(420)], radius=int(P(14)), fill=wc)
    d.rounded_rectangle([P(225), P(432), P(287), P(462)], radius=int(P(12)), fill=wc)
    save_icon(im, "icon_hint")


def icon_ask():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.rounded_rectangle([P(60), P(80), P(452), P(340)], radius=int(P(70)), fill=wc)
    d.polygon([(P(150), P(320)), (P(130), P(450)), (P(260), P(330))], fill=wc)
    cut = (0, 0, 0, 0)
    for x in (160, 256, 352):
        d.ellipse([P(x - 24), P(185), P(x + 24), P(233)], fill=cut)
    save_icon(im, "icon_ask")


def icon_log():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.rounded_rectangle([P(100), P(50), P(412), P(462)], radius=int(P(50)), outline=wc, width=int(P(26)))
    for i, wdt in enumerate((230, 230, 160, 230)):
        y = 140 + i * 76
        d.rounded_rectangle([P(150), P(y), P(150 + wdt), P(y + 26)], radius=int(P(13)), fill=wc)
    save_icon(im, "icon_log")


def icon_back():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.line([(P(330), P(90)), (P(160), P(256)), (P(330), P(422))], fill=wc, width=int(P(56)), joint="curve")
    save_icon(im, "icon_back")


def icon_planet():
    im, d = canvas()
    wc = (255, 255, 255, 255)
    d.ellipse([P(130), P(130), P(382), P(382)], fill=wc)
    d.arc([P(30), P(190), P(482), P(322)], 190, 350, fill=wc, width=int(P(26)))
    d.arc([P(30), P(190), P(482), P(322)], 10, 170, fill=(255, 255, 255, 120), width=int(P(26)))
    save_icon(im, "icon_planet")


if __name__ == "__main__":
    make_nebulae()
    make_horizon()
    make_effect_sprites()
    make_planet_textures()
    make_sky("sky_moon", (0.0, 0.0, 0.02), (0.06, 0.08, 0.18), 5200, 100, nebula=(0.45, 0.25, 0.8, 0.6))
    make_sky("sky_mars", (0.17, 0.08, 0.1), (0.95, 0.58, 0.38), 1100, 110)
    make_sky("sky_orbital", (0.0, 0.0, 0.015), (0.03, 0.06, 0.2), 6500, 120, nebula=(0.25, 0.55, 1.0, 0.7))
    make_sky("sky_europa", (0.01, 0.01, 0.05), (0.18, 0.22, 0.42), 5600, 130, nebula=(0.7, 0.35, 0.6, 0.55))
    for f in (icon_note, icon_speaker):
        f(False)
        f(True)
    for f in (icon_globe, icon_scan, icon_collect, icon_analyze, icon_repair, icon_lock, icon_check, icon_hint,
              icon_ask, icon_log, icon_back, icon_planet):
        f()
    print("art written to", UI, "and", SKY)
