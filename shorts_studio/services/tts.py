from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import edge_tts
from mutagen.mp3 import MP3


_VOICE_CACHE: list[dict[str, Any]] | None = None

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


def _ticks_to_seconds(value: int | float | None) -> float:
    return float(value or 0) / 10_000_000.0


def _rate_for_role(role: str) -> str:
    return {
        "hook": "+12%",
        "setup": "+7%",
        "build": "+9%",
        "reveal": "+6%",
        "payoff": "+4%",
    }.get((role or "").lower(), "+7%")


def _pitch_for_role(role: str) -> str:
    return {
        "hook": "+4Hz",
        "setup": "+1Hz",
        "build": "+2Hz",
        "reveal": "+3Hz",
        "payoff": "+0Hz",
    }.get((role or "").lower(), "+1Hz")


def _naturalize_text(text: str, role: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # Tiny punctuation cleanup helps the neural voice phrase short-form narration
    # without injecting fake filler or changing factual meaning.
    text = text.replace(" - ", " — ")
    if role == "hook" and text and text[-1] not in ".!?":
        text += "."
    return text


async def _voices() -> list[dict[str, Any]]:
    global _VOICE_CACHE
    if _VOICE_CACHE is None:
        try:
            _VOICE_CACHE = await edge_tts.list_voices()
        except Exception:
            _VOICE_CACHE = []
    return _VOICE_CACHE


async def _resolve_voice(requested: str) -> str:
    character_profiles = {
        "character-male-1": MALE_PREFERENCES,
        "character-male-2": (
            "en-US-BrianMultilingualNeural",
            "en-AU-WilliamNeural",
            "en-US-GuyNeural",
            "en-US-AndrewMultilingualNeural",
        ),
        "character-male-3": (
            "en-US-GuyNeural",
            "en-US-AndrewMultilingualNeural",
            "en-AU-WilliamNeural",
            "en-US-BrianMultilingualNeural",
        ),
        "character-female-1": FEMALE_PREFERENCES,
        "character-female-2": (
            "en-US-EmmaMultilingualNeural",
            "en-AU-NatashaNeural",
            "en-US-JennyNeural",
            "en-US-AvaMultilingualNeural",
        ),
    }
    if requested in character_profiles:
        preferred = character_profiles[requested]
        available = await _voices()
        names = {str(v.get("ShortName", "")) for v in available}
        for name in preferred:
            if name in names:
                return name
        return preferred[0]

    if not requested.startswith("auto-youthful-"):
        return requested

    preferred = FEMALE_PREFERENCES if requested.endswith("female") else MALE_PREFERENCES
    available = await _voices()
    names = {str(v.get("ShortName", "")) for v in available}

    for name in preferred:
        if name in names:
            return name

    wanted_gender = "Female" if requested.endswith("female") else "Male"
    candidates = []
    for voice in available:
        name = str(voice.get("ShortName", ""))
        if not name.startswith("en-") or voice.get("Gender") != wanted_gender:
            continue
        tags = voice.get("VoiceTag") or {}
        personalities = " ".join(tags.get("VoicePersonalities") or []).lower()
        score = 0
        for term in ("friendly", "positive", "cheerful", "warm", "lively"):
            if term in personalities:
                score += 2
        if name.startswith("en-US-"):
            score += 1
        candidates.append((score, name))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    return "en-US-GuyNeural" if wanted_gender == "Male" else "en-US-JennyNeural"


async def _render_async(
    text: str,
    voice: str,
    output_path: Path,
    *,
    role: str = "",
) -> dict:
    resolved_voice = await _resolve_voice(voice)
    spoken_text = _naturalize_text(text, role)
    rate = _rate_for_role(role)
    pitch = _pitch_for_role(role)
    if voice.startswith("character-"):
        rate = {
            "hook": "+6%",
            "setup": "+1%",
            "build": "+3%",
            "reveal": "+2%",
            "payoff": "+0%",
        }.get((role or "").lower(), "+2%")
        pitch = {
            "hook": "+2Hz",
            "setup": "+0Hz",
            "build": "+1Hz",
            "reveal": "+1Hz",
            "payoff": "+0Hz",
        }.get((role or "").lower(), "+0Hz")

    communicate = edge_tts.Communicate(
        text=spoken_text,
        voice=resolved_voice,
        rate=rate,
        pitch=pitch,
        volume="+0%",
        boundary="WordBoundary",
    )
    words: list[dict] = []
    with output_path.open("wb") as audio_file:
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

    duration = float(MP3(output_path).info.length)
    return {
        "path": str(output_path),
        "duration": duration,
        "words": words,
        "voice": resolved_voice,
        "requested_voice": voice,
        "rate": rate,
        "pitch": pitch,
        "role": role,
    }


def render_scene(
    text: str,
    voice: str,
    output_path: Path,
    *,
    role: str = "",
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return asyncio.run(
        _render_async(
            text,
            voice,
            output_path,
            role=role,
        )
    )
