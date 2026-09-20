from __future__ import annotations

import asyncio
import importlib.util
import json
import math
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any

import edge_tts
from mutagen.mp3 import MP3

from ..config import settings, ROOT_DIR, STORAGE_ROOT, CACHE_DIR


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
    "auto-youthful-male": "am_puck",
    "human-story-male": "am_puck",
    "auto-youthful-female": "af_heart",
    "human-story-female": "af_heart",
    "character-male-1": "am_michael",
    "character-male-2": "am_fenrir",
    "character-male-3": "am_adam",
    "character-female-1": "af_sarah",
    "character-female-2": "af_bella",
}


def _chatterbox_health() -> dict[str, Any]:
    python_exe = Path(settings.chatterbox_python)
    package_dir = python_exe.parent.parent / "Lib" / "site-packages" / "chatterbox"
    runner = ROOT_DIR / "scripts" / "chatterbox_narrate.py"
    ready = python_exe.exists() and package_dir.exists() and runner.exists()
    missing = []
    if not python_exe.exists():
        missing.append("isolated Python runtime")
    if not package_dir.exists():
        missing.append("chatterbox package")
    if not runner.exists():
        missing.append("Shorts Studio narration runner")
    return {
        "ready": ready,
        "python": str(python_exe),
        "package_dir": str(package_dir),
        "runner": str(runner),
        "runner_ready": runner.exists(),
        "device": settings.chatterbox_device,
        "missing": missing,
        "runtime_patch": "perth-dummy-fallback-v1",
    }


def human_voice_health() -> dict[str, Any]:
    model = Path(settings.kokoro_model_path)
    voices = Path(settings.kokoro_voices_path)
    package_ready = importlib.util.find_spec("kokoro_onnx") is not None
    kokoro_ready = package_ready and model.exists() and voices.exists()
    chatterbox = _chatterbox_health()
    ready = bool(chatterbox["ready"] or kokoro_ready)
    return {
        "ready": ready,
        "backend": "chatterbox" if chatterbox["ready"] else "kokoro-onnx",
        "chatterbox": chatterbox,
        "kokoro_ready": kokoro_ready,
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


def render_story_narration(
    scenes: list[dict[str, Any]],
    voice: str,
    output_path: Path,
) -> dict[str, Any]:
    """Render one uninterrupted narration take; prefer Chatterbox when installed."""
    voice_state = human_voice_health()
    if not voice_state["ready"]:
        raise RuntimeError(
            "No natural narration backend is ready. Run install_natural_voice.bat "
            "or install_human_voice.bat, then restart Shorts Studio."
        )
    if not scenes:
        raise RuntimeError("Story has no narration scenes.")

    lines: list[str] = []
    scene_word_counts: list[int] = []
    for scene in scenes:
        line = re.sub(r"\s+", " ", str(scene.get("narration") or "")).strip()
        if not line:
            line = "..."
        lines.append(line)
        scene_word_counts.append(
            len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", line))
        )

    spoken_text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if spoken_text and spoken_text[-1] not in ".!?":
        spoken_text += "."

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path = output_path.with_suffix(".wav")
    backend = "kokoro-onnx-continuous"
    resolved_voice = KOKORO_VOICES.get(voice, "am_puck")
    backend_error = None

    if voice_state.get("chatterbox", {}).get("ready"):
        text_path = output_path.parent / "story_narration_input.txt"
        text_path.write_text(spoken_text, encoding="utf-8")
        runner = ROOT_DIR / "scripts" / "chatterbox_narrate.py"
        env = os.environ.copy()
        hf_root = (STORAGE_ROOT / "cache" / "huggingface") if STORAGE_ROOT else (CACHE_DIR / "huggingface")
        env["HF_HOME"] = str(hf_root)
        env["HUGGINGFACE_HUB_CACHE"] = str(hf_root / "hub")
        env["TORCH_HOME"] = str((STORAGE_ROOT / "cache" / "torch") if STORAGE_ROOT else (CACHE_DIR / "torch"))
        env["TOKENIZERS_PARALLELISM"] = "false"

        command = [
            str(settings.chatterbox_python),
            str(runner),
            "--text-file", str(text_path),
            "--output", str(wav_path),
            "--device", str(settings.chatterbox_device or "cpu"),
            "--exaggeration", "0.46",
            "--cfg-weight", "0.34",
            "--temperature", "0.72",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3600,
                env=env,
            )
            if result.returncode != 0 or not wav_path.exists():
                raise RuntimeError(
                    (result.stderr or result.stdout or "Chatterbox returned no audio")[-1800:]
                )
            backend = "chatterbox-continuous"
            resolved_voice = "chatterbox-builtin"
        except Exception as exc:
            raise RuntimeError(
                "Natural Chatterbox narration failed. Story Studio stopped instead of silently "
                f"substituting the older synthetic narrator: {exc}"
            ) from exc

    if not wav_path.exists():
        # Legacy safety path only. Story-mode preflight requires Chatterbox, so
        # finished Stories should never reach Kokoro.
        model = _get_kokoro()
        import soundfile as sf

        samples, sample_rate = model.create(
            spoken_text,
            voice=KOKORO_VOICES.get(voice, "am_puck"),
            speed=0.98,
            lang="en-us",
        )
        sf.write(str(wav_path), samples, sample_rate)

    import soundfile as sf

    info = sf.info(str(wav_path))
    duration = float(info.frames) / float(info.samplerate) if info.samplerate else 0.0

    # Align captions to the actual generated narration instead of estimating
    # timing from word length. Clean TTS is ideal for tiny.en alignment.
    master_words: list[dict[str, Any]] = []
    if voice_state.get("chatterbox", {}).get("ready"):
        alignment_path = output_path.parent / "story_narration_alignment.json"
        alignment_runner = ROOT_DIR / "scripts" / "align_narration.py"
        whisper_dir = (
            (STORAGE_ROOT / "cache" / "whisper")
            if STORAGE_ROOT
            else (CACHE_DIR / "whisper")
        )
        whisper_dir.mkdir(parents=True, exist_ok=True)
        try:
            aligned = subprocess.run(
                [
                    str(settings.chatterbox_python),
                    str(alignment_runner),
                    "--audio", str(wav_path),
                    "--output", str(alignment_path),
                    "--model-dir", str(whisper_dir),
                ],
                capture_output=True,
                text=True,
                timeout=1800,
                env=os.environ.copy(),
            )
            if aligned.returncode == 0 and alignment_path.exists():
                payload = json.loads(alignment_path.read_text(encoding="utf-8"))
                candidate_words = payload.get("words") if isinstance(payload, dict) else []
                if isinstance(candidate_words, list) and candidate_words:
                    expected_count = max(1, sum(scene_word_counts))
                    ratio = len(candidate_words) / expected_count
                    if 0.72 <= ratio <= 1.28:
                        master_words = candidate_words
        except Exception:
            master_words = []

    if not master_words:
        master_words = _estimated_word_timings(spoken_text, duration)

    total_expected = sum(scene_word_counts)
    if not master_words or total_expected <= 0:
        raise RuntimeError("Could not create narration word timings.")

    scene_audio: list[dict[str, Any]] = []
    cursor = 0
    for idx, (scene, count) in enumerate(zip(scenes, scene_word_counts)):
        count = max(1, count)
        chunk = master_words[cursor: cursor + count]
        if not chunk:
            chunk = [master_words[min(cursor, len(master_words) - 1)]]

        start = 0.0 if idx == 0 else float(chunk[0]["start"])
        cursor += count
        if idx + 1 < len(scene_word_counts) and cursor < len(master_words):
            end = float(master_words[cursor]["start"])
        else:
            end = duration
        end = max(start + 0.35, end)

        relative_words = [
            {
                "text": word.get("text", ""),
                "start": max(0.0, float(word.get("start", 0)) - start),
                "duration": float(word.get("duration", 0)),
            }
            for word in chunk
        ]

        scene_audio.append(
            {
                "path": str(wav_path),
                "duration": end - start,
                "start": start,
                "end": end,
                "words": relative_words,
                "voice": resolved_voice,
                "requested_voice": voice,
                "role": scene.get("role", ""),
                "backend": backend,
                "speaker": "narrator",
            }
        )

    if scene_audio:
        correction = duration - sum(float(x["duration"]) for x in scene_audio)
        scene_audio[-1]["duration"] = max(
            0.35,
            float(scene_audio[-1]["duration"]) + correction,
        )
        scene_audio[-1]["end"] = duration

    return {
        "path": str(wav_path),
        "duration": duration,
        "words": master_words,
        "voice": resolved_voice,
        "requested_voice": voice,
        "speed": None if backend.startswith("chatterbox") else 0.98,
        "backend": backend,
        "backend_error": backend_error,
        "scene_audio": scene_audio,
        "text": spoken_text,
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
    require_human: bool = False,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    voice_state = human_voice_health()
    kokoro_voice = voice.startswith(("auto-youthful-", "human-story-", "character-"))

    if voice_state["ready"] and kokoro_voice:
        try:
            return _render_kokoro(text, voice, output_path, role=role)
        except Exception as exc:
            if require_human:
                raise RuntimeError(
                    f"Kokoro human narration failed: {exc}. "
                    "Story Studio will not silently replace it with the robotic fallback voice."
                ) from exc
            result = asyncio.run(
                _render_edge_async(text, voice, output_path, role=role)
            )
            result["kokoro_error"] = str(exc)
            return result

    if require_human:
        raise RuntimeError(
            "Human narration backend is not ready. Run install_human_voice.bat "
            "and restart Shorts Studio."
        )

    return asyncio.run(
        _render_edge_async(
            text,
            voice,
            output_path,
            role=role,
        )
    )
