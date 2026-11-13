"""Synthesise Astro Play's music and sound effects from scratch (no samples, no licensing issues).

    python scripts/make_audio.py

Writes WAV files into assets/audio:
  music_menu.wav     calm, epic space-ambient loop (menus / galaxy map)
  music_mission.wav  driving electronic loop (3D missions)
  sfx_*.wav          interface and gameplay sounds
Music loops are seamless: the reverb tail is folded back onto the start of the track.
Requires numpy and scipy (only needed to regenerate the files, not to play the game).
"""
import wave
from pathlib import Path

import numpy as np
from scipy import signal

OUT = Path(__file__).resolve().parent.parent / "assets" / "audio"
OUT.mkdir(parents=True, exist_ok=True)
SR = 32000                   # music sample rate
SFX_SR = 32000
rng = np.random.default_rng(7)


# ----------------------------------------------------------------------------- DSP helpers
def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def t_of(dur, sr=SR):
    return np.arange(int(dur * sr)) / sr


def sine(f, dur, sr=SR, phase=0.0):
    return np.sin(2 * np.pi * f * t_of(dur, sr) + phase)


def saw(f, dur, sr=SR, phase=0.0):
    t = t_of(dur, sr)
    return 2 * ((f * t + phase) % 1.0) - 1


def tri(f, dur, sr=SR):
    return 2 * np.abs(saw(f, dur, sr)) - 1


def supersaw(f, dur, voices=5, spread=0.012, sr=SR):
    out = np.zeros(int(dur * sr))
    for i in range(voices):
        det = (i - (voices - 1) / 2) / max(1, (voices - 1) / 2) * spread
        out += saw(f * (1 + det), dur, sr, phase=rng.random())
    return out / voices


def adsr(n, a, d, s, r, sr=SR):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    a, d, r = min(a, n), min(d, max(0, n - a)), min(r, n)
    env = np.ones(n) * s
    env[:a] = np.linspace(0, 1, a, endpoint=False) if a else env[:a]
    env[a:a + d] = np.linspace(1, s, d, endpoint=False) if d else env[a:a + d]
    if r:
        env[-r:] *= np.linspace(1, 0, r)
    return env


def expdecay(n, tau, sr=SR):
    return np.exp(-np.arange(n) / (tau * sr))


def lowpass(x, fc, order=2, sr=SR):
    sos = signal.butter(order, min(fc, sr * 0.45) / (sr / 2), "low", output="sos")
    return signal.sosfilt(sos, x)


def highpass(x, fc, order=2, sr=SR):
    sos = signal.butter(order, fc / (sr / 2), "high", output="sos")
    return signal.sosfilt(sos, x)


def bandpass(x, lo, hi, order=2, sr=SR):
    sos = signal.butter(order, [lo / (sr / 2), min(hi, sr * 0.45) / (sr / 2)], "band", output="sos")
    return signal.sosfilt(sos, x)


def place(buf, snd, start_s, gain=1.0, pan=0.0, sr=SR):
    """Mix a mono sound into a stereo buffer at start_s with constant-power pan (-1..1)."""
    i = int(start_s * sr)
    if i >= buf.shape[0]:
        return
    n = min(len(snd), buf.shape[0] - i)
    ang = (pan + 1) * np.pi / 4
    buf[i:i + n, 0] += snd[:n] * gain * np.cos(ang)
    buf[i:i + n, 1] += snd[:n] * gain * np.sin(ang)


def reverb(stereo, seconds=3.2, wet=0.35, sr=SR, k=6):
    """Diversity convolution reverb.  One noise-burst impulse response makes sustained, tonal pads swell
    and dip (its frequency response is random), so we blend k independent impulse responses with slowly
    moving equal-power weights.  The coloration averages out and the tail also shimmers a little."""
    n = int(seconds * sr)
    N = stereo.shape[0]
    t = np.arange(N) / sr
    a = np.stack([0.5 + 0.5 * np.cos(2 * np.pi * (t / (3.0 + 0.7 * i) + i / k)) for i in range(k)])
    w = a / np.sqrt((a ** 2).sum(axis=0) + 1e-9)
    out = np.zeros_like(stereo)
    for ch in range(2):
        for i in range(k):
            ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (sr * seconds * 0.28))
            ir = lowpass(ir, 5200, sr=sr)
            f = int(0.012 * sr)
            ir[:f] *= np.linspace(0, 1, f)
            ir /= np.sqrt(np.sum(ir ** 2))
            out[:, ch] += w[i] * signal.fftconvolve(stereo[:, ch], ir)[:N]
    return stereo * (1 - wet) + out * wet * 1.6


def ping_pong(stereo, delay_s, feedback=0.4, mix=0.35, sr=SR):
    d = int(delay_s * sr)
    n = stereo.shape[0]
    wet = np.zeros_like(stereo)
    src = stereo.mean(axis=1)
    for k in range(1, 7):
        idx = k * d
        if idx >= n:
            break
        g = (feedback ** (k - 1)) * mix
        ch = k % 2
        wet[idx:, ch] += src[: n - idx] * g
    return stereo + wet


def fold_tail(stereo, loop_len):
    """Make the render loopable: whatever rings past loop_len is added onto the beginning."""
    body = stereo[:loop_len].copy()
    tail = stereo[loop_len:]
    k = min(len(tail), loop_len)
    body[:k] += tail[:k]
    return body


def soft_limit(x, drive=1.15, peak=0.85):
    y = np.tanh(x * drive)
    return y / max(1e-6, np.max(np.abs(y))) * peak


def write_wav(path, data, sr):
    data = np.atleast_2d(data.T).T if data.ndim == 1 else data
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ----------------------------------------------------------------------------- music
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def n(name, octave):
    base = NOTE[name[0]]
    if len(name) > 1:
        base += 1 if name[1] == "#" else -1
    return 12 * (octave + 1) + base


def pad(notes, dur, level=1.0):
    mix = np.zeros(int(dur * SR))
    for m in notes:
        mix += supersaw(midi(m), dur, voices=5, spread=0.009)
    mix = lowpass(mix / len(notes), 1500)
    return mix * adsr(len(mix), 1.4, 0.8, 0.85, 1.8) * level


def pluck(m, dur=0.6, bright=3500):
    s = tri(midi(m), dur) * 0.7 + saw(midi(m), dur) * 0.3
    s = lowpass(s, bright)
    return s * expdecay(len(s), 0.16) * adsr(len(s), 0.004, 0.0, 1.0, 0.05)


def bell(m, dur=1.8):
    t = t_of(dur)
    f = midi(m)
    s = (np.sin(2 * np.pi * f * t + 2.2 * np.sin(2 * np.pi * f * 3.5 * t) * np.exp(-t * 4)) * 0.6
         + np.sin(2 * np.pi * f * 2 * t) * 0.25 * np.exp(-t * 3))
    return s * np.exp(-t * 2.4) * adsr(len(s), 0.003, 0, 1, 0.1)


def sub(m, dur):
    s = sine(midi(m), dur) + 0.25 * sine(midi(m) * 2, dur)
    return s * adsr(len(s), 0.08, 0.2, 0.9, 0.6)


def kick(dur=0.35):
    t = t_of(dur)
    f = 45 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 11)


def hat(dur=0.07, open_=False):
    d = 0.22 if open_ else dur
    s = highpass(rng.standard_normal(int(d * SR)), 7000)
    return s * expdecay(len(s), 0.025 if not open_ else 0.08)


def clap(dur=0.25):
    s = bandpass(rng.standard_normal(int(dur * SR)), 1100, 4200)
    env = expdecay(len(s), 0.07)
    for k in (0.0, 0.012, 0.024):
        env[int(k * SR):] += 0.5 * expdecay(len(s) - int(k * SR), 0.05)
    return s * env


def render_track(bpm, bars, chords, style):
    beat = 60.0 / bpm
    bar = 4 * beat
    loop_len = int(bars * bar * SR)
    tail = int(4.5 * SR)
    buf = np.zeros((loop_len + tail, 2))
    chords = list(chords) * 2                      # the 4-chord progression plays twice
    chord_bars = bars // len(chords)
    half = len(chords) // 2
    scale = (chord_bars * 4) / 16.0                # melodies are written for 16 beats

    for ci, (root, notes, arp, mel) in enumerate(chords):
        t0 = ci * chord_bars * bar
        dur = chord_bars * bar + 1.6
        place(buf, pad(notes, dur), t0, 0.33 if style == "menu" else 0.26, -0.15)
        place(buf, pad([m + 12 for m in notes[:2]], dur, 0.55), t0, 0.14, 0.4)
        place(buf, sub(root, chord_bars * bar + 0.5), t0, 0.42 if style == "menu" else 0.34)
        bell_note = notes[-1] + 12
        place(buf, bell(bell_note, 2.6), t0, 0.12, 0.35)

        steps = chord_bars * (8 if style == "menu" else 16)
        step_len = beat / 2 if style == "menu" else beat / 4
        for s in range(steps):
            idx = s % len(arp)
            m = arp[idx]
            vel = 0.17 if (s % 4 == 0) else 0.1
            second_half = ci >= half
            if style == "menu" and not second_half and s % 2 == 1:
                continue
            pan = -0.45 if s % 2 == 0 else 0.45
            place(buf, pluck(m, 0.55, 3200 if style == "menu" else 4200), t0 + s * step_len, vel, pan)

        # lead melody: second cycle only for the menu, throughout for missions
        if style == "mission" or ci >= half:
            for (start_beat, m, length) in mel:
                ln = length * scale * beat
                note = bell(m, 2.2) if style == "menu" else lowpass(supersaw(midi(m), ln + 0.4, 3, 0.006), 2600)
                if style == "mission":
                    note = note * adsr(len(note), 0.01, 0.1, 0.7, 0.2)
                place(buf, note, t0 + start_beat * scale * beat, 0.2 if style == "menu" else 0.11, 0.1)

    if style == "mission":
        for b in range(bars):
            bt = b * bar
            for q in range(4):
                place(buf, kick(), bt + q * beat, 0.5, 0.0)
                place(buf, hat(), bt + q * beat + beat / 2, 0.12, 0.3)
                if q % 2 == 1:
                    place(buf, clap(), bt + q * beat, 0.16, -0.1)
            place(buf, hat(open_=True), bt + 3.5 * beat, 0.08, -0.3)
        # pulsing bass line follows the chord roots
        for ci, (root, notes, arp, mel) in enumerate(chords):
            t0 = ci * chord_bars * bar
            for s in range(chord_bars * 8):
                m = root + (12 if s % 8 in (3, 7) else 0)
                b = lowpass(saw(midi(m), beat / 2 * 0.9), 650) * adsr(int(beat / 2 * 0.9 * SR), 0.005, 0.1, 0.6, 0.06)
                place(buf, b, t0 + s * beat / 2, 0.22, 0.0)

    buf = ping_pong(buf, beat * 0.75, 0.42, 0.28 if style == "menu" else 0.2)
    buf = reverb(buf, 3.0 if style == "menu" else 2.0, 0.24 if style == "menu" else 0.2)
    buf = fold_tail(buf, loop_len)
    buf[:, 0] = highpass(buf[:, 0], 45, 1)
    buf[:, 1] = highpass(buf[:, 1], 45, 1)
    buf = soft_limit(buf, 1.1, 0.8)
    f = int(0.008 * SR)                           # 8 ms edge fades: no click when the loop restarts
    ramp = np.linspace(0, 1, f)[:, None]
    buf[:f] *= ramp
    buf[-f:] *= ramp[::-1]
    return buf


def make_music():
    A, F, C, G = ("A", "F", "C", "G")
    # (root, chord tones, arpeggio pattern, melody [(beat in chord block, midi, beats)])
    menu = [
        (n("A", 2), [n("A", 3), n("C", 4), n("E", 4), n("A", 4)], [n("A", 4), n("C", 5), n("E", 5), n("C", 5)],
         [(0, n("E", 5), 3), (4, n("C", 5), 2), (6, n("D", 5), 2), (8, n("E", 5), 4), (12, n("A", 5), 4)]),
        (n("F", 2), [n("F", 3), n("A", 3), n("C", 4), n("F", 4)], [n("F", 4), n("A", 4), n("C", 5), n("A", 4)],
         [(0, n("C", 6), 3), (4, n("A", 5), 2), (6, n("G", 5), 2), (8, n("A", 5), 4), (12, n("C", 6), 4)]),
        (n("C", 3), [n("C", 4), n("E", 4), n("G", 4), n("C", 5)], [n("G", 4), n("C", 5), n("E", 5), n("C", 5)],
         [(0, n("G", 5), 3), (4, n("E", 5), 2), (6, n("D", 5), 2), (8, n("E", 5), 4), (12, n("G", 5), 4)]),
        (n("G", 2), [n("G", 3), n("B", 3), n("D", 4), n("G", 4)], [n("D", 5), n("G", 5), n("B", 4), n("G", 4)],
         [(0, n("B", 5), 3), (4, n("G", 5), 2), (6, n("A", 5), 2), (8, n("B", 5), 4), (12, n("D", 6), 4)]),
    ]
    write_wav(OUT / "music_menu.wav", render_track(96, 16, menu, "menu"), SR)

    mission = [
        (n("E", 2), [n("E", 3), n("G", 3), n("B", 3), n("E", 4)], [n("E", 4), n("B", 4), n("G", 4), n("E", 5), n("B", 4), n("G", 4), n("B", 4), n("E", 5)],
         [(0, n("B", 4), 1.5), (2, n("E", 5), 1.5), (4, n("G", 5), 3), (8, n("F#", 5) if False else n("F", 5) + 1, 2), (10, n("E", 5), 2), (12, n("B", 4), 4)]),
        (n("C", 3), [n("C", 4), n("E", 4), n("G", 4), n("C", 5)], [n("C", 4), n("G", 4), n("E", 4), n("C", 5), n("G", 4), n("E", 4), n("G", 4), n("C", 5)],
         [(0, n("G", 4), 1.5), (2, n("C", 5), 1.5), (4, n("E", 5), 3), (8, n("D", 5), 2), (10, n("C", 5), 2), (12, n("G", 4), 4)]),
        (n("G", 2), [n("G", 3), n("B", 3), n("D", 4), n("G", 4)], [n("G", 4), n("D", 5), n("B", 4), n("G", 5), n("D", 5), n("B", 4), n("D", 5), n("G", 5)],
         [(0, n("D", 5), 1.5), (2, n("G", 5), 1.5), (4, n("B", 5), 3), (8, n("A", 5), 2), (10, n("G", 5), 2), (12, n("D", 5), 4)]),
        (n("D", 3), [n("D", 4), n("F", 4) + 1, n("A", 4), n("D", 5)], [n("D", 4), n("A", 4), n("F", 4) + 1, n("D", 5), n("A", 4), n("F", 4) + 1, n("A", 4), n("D", 5)],
         [(0, n("A", 4), 1.5), (2, n("D", 5), 1.5), (4, n("F", 5) + 1, 3), (8, n("E", 5), 2), (10, n("D", 5), 2), (12, n("A", 4), 4)]),
    ]
    write_wav(OUT / "music_mission.wav", render_track(108, 16, mission, "mission"), SR)


# ----------------------------------------------------------------------------- sound effects
def fx(data, gain=0.9):
    data = data / max(1e-6, np.max(np.abs(data))) * gain
    return data


def sfx_click():
    t = t_of(0.07)
    s = np.sin(2 * np.pi * (1500 - 7000 * t) * t) * np.exp(-t * 55)
    return fx(s, 0.7)


def sfx_hover():
    t = t_of(0.05)
    return fx(np.sin(2 * np.pi * 2100 * t) * np.exp(-t * 90), 0.35)


def sfx_open():
    d = 0.28
    s = bandpass(rng.standard_normal(int(d * SR)), 500, 5000)
    s *= np.sin(np.linspace(0, np.pi, len(s))) ** 1.5
    t = t_of(d)
    s += 0.5 * np.sin(2 * np.pi * (300 + 900 * t) * t) * np.exp(-t * 8)
    return fx(s, 0.6)


def sfx_type():
    t = t_of(0.03)
    return fx(np.sin(2 * np.pi * 900 * t) * np.exp(-t * 130) + 0.3 * rng.standard_normal(len(t)) * np.exp(-t * 200), 0.4)


def sfx_scan():
    d = 0.7
    t = t_of(d)
    f = 400 * (6 ** (t / d))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.6 + 0.4 * np.sin(2 * np.pi * 14 * t))
    s *= np.sin(np.linspace(0, np.pi, len(t))) ** 0.7
    s += 0.12 * highpass(rng.standard_normal(len(t)), 5000) * np.exp(-((t - d * 0.85) / 0.1) ** 2)
    ping = bell(n("E", 7), 0.5)
    out = s.copy()
    k = int(d * 0.8 * SR)
    out[k:k + len(ping)] += ping[: len(out) - k] * 0.5
    return fx(lowpass(out, 9000), 0.7)


def sfx_collect():
    t = t_of(0.12)
    pop = np.sin(2 * np.pi * (200 + 1600 * t) * t) * np.exp(-t * 28)
    s = np.concatenate([pop, np.zeros(int(0.02 * SR))])
    for i, m in enumerate((n("E", 5), n("A", 5))):
        b = (sine(midi(m), 0.22) + 0.3 * sine(midi(m) * 2, 0.22)) * expdecay(int(0.22 * SR), 0.09)
        out = np.zeros(len(s) + len(b))
        out[:len(s)] = s
        k = int((0.04 + i * 0.07) * SR) + len(pop)
        out = np.pad(out, (0, max(0, k + len(b) - len(out))))
        out[k:k + len(b)] += b * 0.6
        s = out
    return fx(s, 0.75)


def sfx_analyze():
    notes = [n("C", 6), n("E", 6), n("G", 6), n("E", 6), n("A", 6), n("G", 6), n("C", 7)]
    out = np.zeros(int(0.9 * SR))
    for i, m in enumerate(notes):
        s = sine(midi(m), 0.08) * adsr(int(0.08 * SR), 0.003, 0, 1, 0.02)
        k = int(i * 0.075 * SR)
        out[k:k + len(s)] += s * 0.55
    out += 0.12 * bandpass(rng.standard_normal(len(out)), 2500, 7000) * np.sin(np.linspace(0, np.pi, len(out)))
    return fx(out, 0.7)


def chord_arp(notes, step=0.07, ring=0.7, wave_fn=bell):
    out = np.zeros(int((step * len(notes) + ring) * SR))
    for i, m in enumerate(notes):
        b = wave_fn(m, ring)
        k = int(i * step * SR)
        out[k:k + len(b)] += b[: len(out) - k]
    return out


def sfx_success():
    return fx(chord_arp([n("C", 5), n("E", 5), n("G", 5), n("C", 6)], 0.07, 0.8), 0.8)


def sfx_repair():
    a = chord_arp([n("C", 5), n("G", 5), n("E", 6), n("G", 6), n("C", 7)], 0.075, 1.2)
    t = t_of(len(a) / SR)
    pad_ = lowpass(supersaw(midi(n("C", 4)), len(a) / SR, 5, 0.01) + supersaw(midi(n("G", 4)), len(a) / SR, 5, 0.01), 2200)
    pad_ *= adsr(len(pad_), 0.05, 0.3, 0.5, 0.7)
    return fx(a * 0.8 + pad_ * 0.25, 0.8)


def sfx_error():
    d = 0.4
    t = t_of(d)
    f = 240 * np.exp(-t * 2.2)
    s = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.5 + np.sin(2 * np.pi * np.cumsum(f * 0.5) / SR) * 0.5
    s = lowpass(s, 1400) * adsr(len(t), 0.005, 0.1, 0.8, 0.12)
    return fx(s, 0.7)


def sfx_hint():
    out = chord_arp([n("G", 6), n("D", 7)], 0.09, 0.6)
    return fx(out, 0.55)


def sfx_launch():
    d = 2.2
    t = t_of(d)
    noise = rng.standard_normal(len(t))
    sweep = np.zeros_like(noise)
    blocks = 40
    for i in range(blocks):
        a, b = int(i * len(t) / blocks), int((i + 1) * len(t) / blocks)
        fc = 200 + 5200 * (i / blocks) ** 2
        sweep[a:b] = lowpass(noise[a:b], fc, 1)
    rumble = lowpass(noise, 140) * 2.0
    s = (sweep * 0.8 + rumble * 0.9) * (np.minimum(1, t / 1.6) ** 1.5) * np.exp(-np.maximum(0, t - 1.7) * 6)
    s += 0.4 * np.sin(2 * np.pi * np.cumsum(60 + 380 * (t / d) ** 2) / SR) * np.minimum(1, t / 1.0)
    return fx(s, 0.85)


def sfx_fanfare():
    seq = [(0.0, [n("C", 4), n("E", 4), n("G", 4)], 0.9), (0.35, [n("F", 4), n("A", 4), n("C", 5)], 0.9),
           (0.7, [n("G", 4), n("B", 4), n("D", 5)], 0.9), (1.1, [n("C", 5), n("E", 5), n("G", 5), n("C", 6)], 2.4)]
    out = np.zeros(int(4.2 * SR))
    for start, notes, dur in seq:
        for m in notes:
            s = lowpass(supersaw(midi(m), dur, 4, 0.007), 3200) * adsr(int(dur * SR), 0.02, 0.2, 0.7, 0.6)
            k = int(start * SR)
            out[k:k + len(s)] += s * 0.28
    out += chord_arp([n("C", 6), n("E", 6), n("G", 6), n("C", 7), n("E", 7)], 0.09, 1.6)[: len(out)] * 0.5 if False else 0
    arp = chord_arp([n("C", 6), n("E", 6), n("G", 6), n("C", 7), n("E", 7)], 0.09, 1.6)
    k = int(1.1 * SR)
    out[k:k + len(arp)] += arp[: len(out) - k] * 0.55
    return fx(out, 0.85)


def sfx_star():
    return fx(chord_arp([n("A", 6), n("E", 7)], 0.06, 0.7), 0.7)


def sfx_levelup():
    return fx(chord_arp([n("C", 5), n("E", 5), n("G", 5), n("C", 6), n("E", 6), n("G", 6)], 0.06, 1.0), 0.8)


def make_sfx():
    items = {"click": sfx_click, "hover": sfx_hover, "open": sfx_open, "type": sfx_type, "scan": sfx_scan,
             "collect": sfx_collect, "analyze": sfx_analyze, "success": sfx_success, "repair": sfx_repair,
             "error": sfx_error, "hint": sfx_hint, "launch": sfx_launch, "fanfare": sfx_fanfare,
             "star": sfx_star, "levelup": sfx_levelup}
    for name, fn in items.items():
        write_wav(OUT / f"sfx_{name}.wav", fn(), SFX_SR)


if __name__ == "__main__":
    make_sfx()
    make_music()
    for p in sorted(OUT.glob("*.wav")):
        print(f"{p.name:22s} {p.stat().st_size / 1024:8.0f} KB")
