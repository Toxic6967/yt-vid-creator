from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


def _ticks_to_seconds(value: int | float | None) -> float:
    # Edge TTS reports offsets/durations in 100-nanosecond ticks.
    return float(value or 0) / 10_000_000.0


async def _render_async(text: str, voice: str, output_path: Path) -> dict:
    communicate = edge_tts.Communicate(text=text, voice=voice)
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
    return {"path": str(output_path), "duration": duration, "words": words}


def render_scene(text: str, voice: str, output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_render_async(text, voice, output_path))
