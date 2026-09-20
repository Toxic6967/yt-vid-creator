from __future__ import annotations

import asyncio
import importlib.util
import math
import re
import threading
from pathlib import Path
from typing import Any

import edge_tts
from mutagen.mp3 import MP3

from ..config import settings


_VOICE_CACHE: list[dict[str, Any]] | None = None
_KOKORO: Any | None = None
_KOKORO_LOCK = threading.Lock()

MALE_PREFERENCES = (
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-GuyNeural",
    "en-AU-WilliamNeural",
)

FEMALE_PREFERENCES = (
    "en-US-AvaMultilingualNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-JennyNeural",
    "en-AU-NatashaNeural",
)

KOKORO_VOICES = {
    "auto-youthful-male": "am_michael",
    "human-story-male": "am_michael",
    "auto-youthful-female": "af_sarah",
    "human-story-female": "af_sarah",
    "character-male-1": "am_michael",
    "character-male-2": "am_fenrir",
    "character-male-3": "am_adam",
    "character-female-1": "af_sarah",
    "character-female-2": "af_bella",
}


def human_voice_health() -> dict[str, Any]:
    model = Path(settings.kokoro_model_path)
    voices = Path(settings.kokoro_voices_path)
    package_ready = importlib.util.find_spec("kokoro_onnx") is not None
    ready = package_ready and model.exists() and voices.exists()
    return {
        "ready": ready,
        "backend": "kokoro-onnx",
        "package_ready": package_ready,
        "model_ready": model.exists(),
        "voices_ready": voices.exists(),
        "model_path": str(model),
        "voices_path": str(voices),
    }


def _ticks_to_seconds(value: int | float | None) -> float:
    return float(value or 0) / 10_000_000.0


def _naturalize_text(text: str, role: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.replace(" - ", " — ")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _kokoro_speed(role: str) -> float:
    # Deliberately close to natural speech. Previous +6–12% Edge rates
    # sounded like an AI Shorts announcer.
    return {
        "hook": 1.03,
        "setup": 0.99,
        "build": 1.01,
        "reveal": 0.98,
        "payoff": 0.97,
    }.get((role or "").lower(), 1.0)


def _estimated_word_timings(text: str, duration: float) -> list[dict[str, Any]]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*[.,!?;:]?", text)
    if not tokens or duration <= 0:
        return []

    weights = []
    for token in tokens:
        clean = re.sub(r"[^A-Za-z0-9'_-]", "", token)
        weight = max(0.72, math.sqrt(max(1, len(clean))) * 0.78)
        if token.endswith((",", ";", ":")):
            weight += 0.42
        elif token.endswith((".", "!", "?")):
            weight += 0.78
        weights.append(weight)

    total = sum(weights) or 1.0
    cursor = 0.0
    out: list[dict[str, Any]] = []
    for token, weight in zip(tokens, weights):
        span = duration * (weight / total)
        spoken = re.sub(r"[.,!?;:]+$", "", token)
        out.append(
            {
                "text": spoken,
                "start": cursor,
                "duration": max(0.08, span),
            }
        )
        cursor += span

    if out:
        out[-1]["duration"] = max(0.08, duration - float(out[-1]["start"]))
    return out


def _get_kokoro() -> Any:
    global _KOKORO
    with _KOKORO_LOCK:
        if _KOKORO is None:
            from kokoro_onnx import Kokoro

            _KOKORO = Kokoro(
                settings.kokoro_model_path,
                settings.kokoro_voices_path,
            )
        return _KOKORO


def _render_kokoro(
    text: str,
    voice: str,
    output_path: Path,
    *,
    role: str = "",
) -> dict[str, Any]:
    import soundfile as sf

    spoken_text = _naturalize_text(text, role)
    resolved_voice = KOKORO_VOICES.get(voice, "am_michael")
    speed = _kokoro_speed(role)
    wav_path = output_path.with_suffix(".wav")
    wav_path.parent.mkdir(parents=True, exist_ok=True)

    model = _get_kokoro()
    samples, sample_rate = model.create(
        spoken_text,
        voice=resolved_voice,
        speed=speed,
        lang="en-us",
    )
    sf.write(str(wav_path), samples, sample_rate)

    frames = len(samples)
    duration = float(frames) / float(sample_rate) if sample_rate else 0.0
    words = _estimated_word_timings(spoken_text, duration)
    return {
        "path": str(wav_path),
        "duration": duration,
        "words": words,
        "voice": resolved_voice,
        "requested_voice": voice,
        "speed": speed,
        "role": role,
        "backend": "kokoro-onnx",
    }


def _rate_for_role(role: str) -> str:
    return {
        "hook": "+4%",
        "setup": "+0%",
        "build": "+2%",
        "reveal": "+0%",
        "payoff": "-1%",
    }.get((role or "").lower(), "+0%")


def _pitch_for_role(role: str) -> str:
    return {
        "hook": "+1Hz",
        "setup": "+0Hz",
        "build": "+0Hz",
        "reveal": "+0Hz",
        "payoff": "+0Hz",
    }.get((role or "").lower(), "+0Hz")


async def _voices() -> list[dict[str, Any]]:
    global _VOICE_CACHE
    if _VOICE_CACHE is None:
        try:
            _VOICE_CACHE = await edge_tts.list_voices()
        except Exception:
            _VOICE_CACHE = []
    return _VOICE_CACHE


async def _resolve_edge_voice(requested: str) -> str:
    if requested.startswith("character-female") or requested.endswith("female"):
        preferred = FEMALE_PREFERENCES
    else:
        preferred = MALE_PREFERENCES

    if not requested.startswith(("auto-youthful-", "human-story-", "character-")):
        return requested

    available = await _voices()
    names = {str(v.get("ShortName", "")) for v in available}
    for name in preferred:
        if name in names:
            return name
    return preferred[0]


async def _render_edge_async(
    text: str,
    voice: str,
    output_path: Path,
    *,
    role: str = "",
) -> dict[str, Any]:
    resolved_voice = await _resolve_edge_voice(voice)
    spoken_text = _naturalize_text(text, role)
    rate = _rate_for_role(role)
    pitch = _pitch_for_role(role)
    mp3_path = output_path.with_suffix(".mp3")
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(
        text=spoken_text,
        voice=resolved_voice,
        rate=rate,
        pitch=pitch,
        volume="+0%",
        boundary="WordBoundary",
    )
    words: list[dict[str, Any]] = []
    with mp3_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(
                    {
                        "text": chunk.get("text", ""),
                        "start": _ticks_to_seconds(chunk.get("offset")),
                        "duration": _ticks_to_seconds(chunk.get("duration")),
                    }
                )

    duration = float(MP3(mp3_path).info.length)
    return {
        "path": str(mp3_path),
        "duration": duration,
        "words": words,
        "voice": resolved_voice,
        "requested_voice": voice,
        "rate": rate,
        "pitch": pitch,
        "role": role,
        "backend": "edge-tts-fallback",
    }


def render_scene(
    text: str,
    voice: str,
    output_path: Path,
    *,
    role: str = "",
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if human_voice_health()["ready"] and voice.startswith(
        ("auto-youthful-", "human-story-", "character-")
    ):
        try:
            return _render_kokoro(text, voice, output_path, role=role)
        except Exception as exc:
            # Preserve a useful reason in the fallback metadata rather than
            # taking down non-Story legacy workflows.
            result = asyncio.run(
                _render_edge_async(text, voice, output_path, role=role)
            )
            result["kokoro_error"] = str(exc)
            return result

    return asyncio.run(
        _render_edge_async(
            text,
            voice,
            output_path,
            role=role,
        )
    )
