from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

from ..config import SFX_DIR

SAMPLE_RATE = 44100


def _write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for value in samples:
            value = max(-1.0, min(1.0, value))
            frames.extend(struct.pack("<h", int(value * 32767)))
        wav.writeframes(bytes(frames))


def _fade_envelope(i: int, total: int, attack: float = 0.08, release: float = 0.55) -> float:
    t = i / max(1, total - 1)
    a = min(1.0, t / max(0.001, attack))
    r = min(1.0, (1.0 - t) / max(0.001, release))
    return max(0.0, min(a, r))


def _whoosh(path: Path) -> None:
    total = int(SAMPLE_RATE * 0.42)
    smooth = 0.0
    samples = []
    rng = random.Random(1701)
    for i in range(total):
        t = i / SAMPLE_RATE
        smooth = smooth * 0.88 + rng.uniform(-1, 1) * 0.12
        sweep = math.sin(2 * math.pi * (180 + 1100 * (t / 0.42) ** 1.8) * t)
        env = math.sin(math.pi * min(1.0, t / 0.42)) ** 1.4
        samples.append((smooth * 0.62 + sweep * 0.15) * env * 0.68)
    _write_wav(path, samples)


def _impact(path: Path) -> None:
    total = int(SAMPLE_RATE * 0.32)
    samples = []
    rng = random.Random(211)
    for i in range(total):
        t = i / SAMPLE_RATE
        env = math.exp(-13 * t)
        low = math.sin(2 * math.pi * (78 - 22 * min(1, t / 0.32)) * t)
        noise = rng.uniform(-1, 1) * math.exp(-22 * t)
        samples.append((low * 0.78 + noise * 0.24) * env)
    _write_wav(path, samples)


def _alert(path: Path) -> None:
    total = int(SAMPLE_RATE * 0.45)
    samples = []
    for i in range(total):
        t = i / SAMPLE_RATE
        tone = 0.0
        if 0.02 < t < 0.14:
            tone = math.sin(2 * math.pi * 720 * t)
        elif 0.19 < t < 0.34:
            tone = math.sin(2 * math.pi * 940 * t)
        samples.append(tone * 0.45)
    _write_wav(path, samples)


def _glitch(path: Path) -> None:
    total = int(SAMPLE_RATE * 0.30)
    samples = []
    rng = random.Random(404)
    held = 0.0
    for i in range(total):
        if i % 120 == 0:
            held = rng.uniform(-1, 1)
        t = i / SAMPLE_RATE
        gate = 1.0 if int(t * 42) % 2 == 0 else 0.18
        env = 1.0 - min(1.0, t / 0.30)
        samples.append(held * gate * env * 0.50)
    _write_wav(path, samples)


def _win(path: Path) -> None:
    total = int(SAMPLE_RATE * 0.62)
    notes = (523.25, 659.25, 783.99)
    samples = []
    for i in range(total):
        t = i / SAMPLE_RATE
        idx = min(2, int(t / 0.18))
        local = t - idx * 0.18
        env = math.exp(-5.5 * max(0, local))
        samples.append(math.sin(2 * math.pi * notes[idx] * t) * env * 0.36)
    _write_wav(path, samples)


def ensure_builtin_sfx() -> dict[str, Path]:
    files = {
        "whoosh": SFX_DIR / "builtin_whoosh.wav",
        "impact": SFX_DIR / "builtin_impact.wav",
        "alert": SFX_DIR / "builtin_alert.wav",
        "glitch": SFX_DIR / "builtin_glitch.wav",
        "win": SFX_DIR / "builtin_win.wav",
    }
    makers = {
        "whoosh": _whoosh,
        "impact": _impact,
        "alert": _alert,
        "glitch": _glitch,
        "win": _win,
    }
    for key, path in files.items():
        if not path.exists():
            makers[key](path)
    return files


def pick_sfx(cue: str | None) -> Path | None:
    cue = (cue or "").strip().lower()
    if not cue:
        return None

    files = ensure_builtin_sfx()
    groups = (
        ("glitch", ("lag", "glitch", "disconnect", "error", "freeze", "static")),
        ("alert", ("beep", "alert", "message", "notification", "ping", "warning")),
        ("win", ("win", "victory", "rare", "reward", "success", "unlock")),
        ("impact", ("hit", "slam", "impact", "bang", "door", "scare", "jump", "crash")),
        ("whoosh", ("whoosh", "swish", "reveal", "transition", "zoom", "rush")),
    )
    for key, markers in groups:
        if any(marker in cue for marker in markers):
            return files[key]
    return files["whoosh"]
