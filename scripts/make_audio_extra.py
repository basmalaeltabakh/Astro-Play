"""Extra procedural sound effects for the astronaut / habitat update (breathing, footsteps, doors, alarms...).

    python scripts/make_audio_extra.py

Separate from make_audio.py on purpose: it has its own random generator so re-running it never changes the
existing music or sound effects.  Writes assets/audio/sfx_*.wav.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_audio as M  # noqa: E402  (reuses its synth helpers only)

OUT = M.OUT
SR = M.SR
rng = np.random.default_rng(2112)


def noise(n):
    return rng.standard_normal(int(n))


def norm(x, g=0.8):
    return x / max(1e-6, np.max(np.abs(x))) * g


def mix_at(out, snd, t, gain=1.0):
    i = int(t * SR)
    n = max(0, min(len(snd), len(out) - i))
    if n:
        out[i:i + n] += snd[:n] * gain


# ---------------------------------------------------------------- footsteps (3 variants per surface)
def step(surface, v):
    d = 0.22
    n = int(d * SR)
    t = np.arange(n) / SR
    r = 1 + 0.12 * (v - 1)
    if surface == "dust":        # soft thud with a little powdery crunch (Moon)
        body = M.lowpass(noise(n), 260 * r) * np.exp(-t * 26)
        thump = np.sin(2 * np.pi * 70 * r * t) * np.exp(-t * 30)
        crunch = M.bandpass(noise(n), 1500, 4500) * np.exp(-t * 45) * 0.18
        s = body * 1.4 + thump * 0.8 + crunch
    elif surface == "gravel":    # Mars: grittier crunch
        body = M.lowpass(noise(n), 500 * r) * np.exp(-t * 20)
        grit = M.bandpass(noise(n), 1800, 6500) * np.exp(-t * 17) * (0.6 + 0.4 * np.sin(2 * np.pi * 38 * t))
        s = body * 1.0 + grit * 0.55 + np.sin(2 * np.pi * 85 * r * t) * np.exp(-t * 32) * 0.5
    elif surface == "ice":       # Europa: squeaky crunch with a bright tick
        crunch = M.bandpass(noise(n), 2200, 8000) * np.exp(-t * 22) * (0.5 + 0.5 * np.sin(2 * np.pi * 55 * t))
        squeak = np.sin(2 * np.pi * (2400 * r + 600 * t * 10) * t) * np.exp(-t * 40) * 0.25
        s = crunch + squeak + M.lowpass(noise(n), 300) * np.exp(-t * 28) * 0.6
    else:                        # metal: hollow clank (habitat floor / station hull)
        f = 190 * r
        s = (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 2.76 * t) + 0.3 * np.sin(2 * np.pi * f * 5.4 * t))
        s = s * np.exp(-t * 30) + M.bandpass(noise(n), 900, 4000) * np.exp(-t * 60) * 0.4
    s = s * M.adsr(n, 0.001, 0.01, 0.9, 0.04)
    return norm(s, 0.7)


# ---------------------------------------------------------------- breathing (inside the helmet)
def breath(dur_in, dur_out, rate=1.0, level=0.5):
    n_in, n_out = int(dur_in * SR / rate), int(dur_out * SR / rate)
    ins = M.bandpass(noise(n_in), 350, 2600) * np.sin(np.linspace(0, np.pi, n_in)) ** 1.6
    outs = M.bandpass(noise(n_out), 250, 2000) * np.sin(np.linspace(0, np.pi, n_out)) ** 1.3 * 0.8
    gap = np.zeros(int(0.12 * SR / rate))
    s = np.concatenate([ins * 0.8, gap, outs])
    hum = M.lowpass(noise(len(s)), 150) * 0.15                  # faint suit air-circulation rumble
    return norm((s + hum) * level, 0.55)


# ---------------------------------------------------------------- tools and interactions
def sfx_wrench():
    out = np.zeros(int(0.75 * SR))
    for k in range(4):                                         # ratchet clicks
        t = np.arange(int(0.05 * SR)) / SR
        c = (np.sin(2 * np.pi * (1800 + 120 * k) * t) + 0.5 * np.sin(2 * np.pi * 3400 * t)) * np.exp(-t * 90)
        mix_at(out, c, 0.04 + k * 0.1, 0.55)
    t = np.arange(int(0.4 * SR)) / SR
    clank = (np.sin(2 * np.pi * 420 * t) + 0.7 * np.sin(2 * np.pi * 1130 * t) + 0.4 * np.sin(2 * np.pi * 2300 * t)) * np.exp(-t * 9)
    mix_at(out, clank, 0.4, 0.7)
    return norm(out, 0.8)


def sfx_equip():
    d = 0.22
    t = np.arange(int(d * SR)) / SR
    click = np.sin(2 * np.pi * (900 - 2500 * t) * t) * np.exp(-t * 40)
    sw = M.bandpass(noise(len(t)), 600, 3500) * np.sin(np.linspace(0, np.pi, len(t))) * 0.35
    return norm(click + sw, 0.6)


def sfx_door(opening=True):
    d = 1.1
    n = int(d * SR)
    t = np.arange(n) / SR
    hiss = M.highpass(noise(n), 2500) * np.exp(-t * 3.2) * 0.5
    motor = M.lowpass(M.saw(95 * (1 + 0.25 * (t / d if opening else 1 - t / d)), d), 700) * np.sin(np.linspace(0, np.pi, n)) ** 0.7 * 0.45
    thunk = np.zeros(n)
    k = np.arange(int(0.14 * SR)) / SR
    mix_at(thunk, np.sin(2 * np.pi * 85 * k) * np.exp(-k * 30), d - 0.16 if opening else 0.0, 0.9)
    mix_at(thunk, np.sin(2 * np.pi * 85 * k) * np.exp(-k * 30), 0.02 if opening else d - 0.16, 0.9)
    return norm(hiss + motor + thunk, 0.8)


def sfx_bed():
    d = 1.6
    n = int(d * SR)
    t = np.arange(n) / SR
    rustle = M.bandpass(noise(n), 800, 3500) * (np.sin(2 * np.pi * 6 * t) ** 2) * np.exp(-t * 1.5) * 0.4
    tone = (M.sine(220, d) + M.sine(329.6, d) * 0.7 + M.sine(440, d) * 0.4) * np.sin(np.linspace(0, np.pi, n)) ** 2 * 0.35
    return norm(rustle + tone, 0.6)


def sfx_locker():
    d = 1.0
    n = int(d * SR)
    t = np.arange(n) / SR
    sweep = np.sin(2 * np.pi * np.cumsum(300 + 1500 * (t / d) ** 1.5) / SR) * np.sin(np.linspace(0, np.pi, n)) ** 0.6 * 0.5
    out = sweep.copy()
    for tt in (0.0, d - 0.18):                                  # latch clacks
        k = np.arange(int(0.1 * SR)) / SR
        mix_at(out, (np.sin(2 * np.pi * 700 * k) + 0.5 * np.sin(2 * np.pi * 1900 * k)) * np.exp(-k * 55), tt, 0.7)
    mix_at(out, M.bell(M.midi(88) if False else 88, 0.6)[: int(0.5 * SR)], d - 0.5, 0.0)
    ding = M.bell(88, 0.7)
    mix_at(out, ding, d - 0.3, 0.5)
    return norm(out[: int(1.3 * SR)], 0.75)


def sfx_o2fill():
    d = 2.4
    n = int(d * SR)
    t = np.arange(n) / SR
    hiss = M.highpass(noise(n), 1800) * (0.6 + 0.4 * (t / d)) * 0.5
    flow = M.bandpass(noise(n), 300, 1200) * 0.35
    env = np.minimum(1, t / 0.08) * np.minimum(1, (d - t) / 0.15)
    return norm((hiss + flow) * env, 0.6)


def sfx_alarm(kind):
    if kind == "low":
        out = np.zeros(int(0.9 * SR))
        for i in range(2):
            b = M.sine(880, 0.16) * M.adsr(int(0.16 * SR), 0.005, 0.02, 0.8, 0.06)
            mix_at(out, b, i * 0.22, 0.7)
        return norm(out, 0.55)
    out = np.zeros(int(1.0 * SR))
    for i in range(3):
        b = (M.sine(1320, 0.12) + 0.4 * M.sine(1980, 0.12)) * M.adsr(int(0.12 * SR), 0.003, 0.02, 0.9, 0.04)
        mix_at(out, b, i * 0.16, 0.8)
    return norm(out, 0.75)


def sfx_lab():
    d = 1.8
    n = int(d * SR)
    t = np.arange(n) / SR
    hum = (M.sine(110, d) * 0.5 + M.lowpass(M.saw(220, d), 900) * 0.25) * np.sin(np.linspace(0, np.pi, n)) ** 0.5
    blips = np.zeros(n)
    for i in range(7):
        mix_at(blips, M.sine(1200 + (i % 3) * 300, 0.05) * np.exp(-np.arange(int(0.05 * SR)) / (0.02 * SR)), 0.15 + i * 0.13, 0.35)
    out = hum * 0.6 + blips
    mix_at(out, M.bell(84, 0.9), 1.15, 0.55)
    return norm(out, 0.75)


def sfx_land():
    d = 0.3
    n = int(d * SR)
    t = np.arange(n) / SR
    s = M.lowpass(noise(n), 320) * np.exp(-t * 18) * 1.3 + np.sin(2 * np.pi * 60 * t) * np.exp(-t * 22)
    return norm(s, 0.75)


def main():
    files = {}
    for surf in ("dust", "gravel", "ice", "metal"):
        for v in range(3):
            files[f"step_{surf}_{v}"] = step(surf, v)
    files["breath"] = breath(1.3, 1.9, 1.0, 0.55)
    files["breath_fast"] = breath(0.75, 0.95, 1.0, 0.8)
    files["wrench"] = sfx_wrench()
    files["equip"] = sfx_equip()
    files["door_open"] = sfx_door(True)
    files["door_close"] = sfx_door(False)
    files["bed"] = sfx_bed()
    files["locker"] = sfx_locker()
    files["o2fill"] = sfx_o2fill()
    files["alarm_low"] = sfx_alarm("low")
    files["alarm_crit"] = sfx_alarm("crit")
    files["lab"] = sfx_lab()
    files["land"] = sfx_land()
    for name, data in files.items():
        M.write_wav(OUT / f"sfx_{name}.wav", data, SR)
    print(f"wrote {len(files)} sound effects to {OUT}")


if __name__ == "__main__":
    main()
