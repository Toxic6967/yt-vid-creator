from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

import imageio_ffmpeg

from ..config import MUSIC_DIR
from .sfx import pick_sfx


def ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg_health() -> dict:
    try:
        exe = ffmpeg_path()
        result = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=8)
        first = (result.stdout or result.stderr).splitlines()[0]
        return {"ok": result.returncode == 0, "path": exe, "version": first}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _run(args: list[str], cwd: Path | None = None) -> None:
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *args]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-1800:]}")


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", " ")


def _caption_chunks(words: list[dict], max_words: int = 4) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        current.append(word)
        text = str(word.get("text", ""))
        ends_phrase = text.endswith((".", "!", "?", ",", ":", ";"))
        if len(current) >= max_words or (ends_phrase and len(current) >= 2):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _caption_phrase(chunk: list[dict], active_index: int, role: str, emphasis: str) -> str:
    active_colour = "&H0000D7FF&"
    if role in {"reveal", "payoff"}:
        active_colour = "&H006B7CFF&"
    elif role == "hook":
        active_colour = "&H00FFF27A&"

    emphasis_words = {
        token.strip(".,!?;:'\\\"").lower()
        for token in str(emphasis or "").split()
        if token.strip()
    }

    rendered: list[str] = []
    for i, item in enumerate(chunk):
        raw = str(item.get("text", "")).strip()
        clean = raw.strip(".,!?;:'\\\"").lower()
        text = _ass_escape(raw)
        if i == active_index:
            scale = 124 if (clean in emphasis_words or role in {"hook", "reveal", "payoff"}) else 114
            rendered.append(
                r"{\c" + active_colour
                + r"\fscx" + str(scale)
                + r"\fscy" + str(scale)
                + r"\bord7\shad2}"
                + text
                + r"{\rMain}"
            )
        else:
            rendered.append(text)

    if len(rendered) == 4:
        return " ".join(rendered[:2]) + r"\N" + " ".join(rendered[2:])
    return " ".join(rendered)


def build_captions(
    scene_audio: list[dict],
    caption_path: Path,
    scenes: list[dict] | None = None,
) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Main,Arial,80,&H00FFFFFF,&H00FFFFFF,&H00101010,&H60000000,-1,0,0,0,100,100,0,0,1,7,2,2,88,88,330,1
Style: Hook,Arial,88,&H00FFFFFF,&H00FFFFFF,&H00101010,&H70000000,-1,0,0,0,100,100,0,0,1,8,2,2,82,82,340,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    timeline = 0.0

    for scene_index, audio in enumerate(scene_audio):
        scene = (scenes or [])[scene_index] if scenes and scene_index < len(scenes) else {}
        role = str(scene.get("role") or audio.get("role") or "").lower()
        emphasis = str(scene.get("on_screen_emphasis") or "")
        style = "Hook" if role in {"hook", "reveal", "payoff"} else "Main"

        words = [w for w in audio.get("words", []) if str(w.get("text", "")).strip()]
        if not words:
            timeline += float(audio.get("duration", 0))
            continue

        max_words = 3 if scene.get("game_name") or scene.get("character_visuals") else 4
        for chunk in _caption_chunks(words, max_words=max_words):
            chunk_end = (
                timeline
                + float(chunk[-1].get("start", 0))
                + max(0.16, float(chunk[-1].get("duration", 0)))
            )
            for active_index, word in enumerate(chunk):
                start = timeline + float(word.get("start", 0))
                if active_index + 1 < len(chunk):
                    end = timeline + float(chunk[active_index + 1].get("start", 0))
                else:
                    end = chunk_end
                end = max(start + 0.11, end)

                phrase = _caption_phrase(chunk, active_index, role, emphasis)
                entrance = (
                    r"{\fad(20,25)\fscx90\fscy90\t(0,85,\fscx100\fscy100)}"
                    if active_index == 0
                    else ""
                )
                lines.append(
                    f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,"
                    f"{entrance}{phrase}\n"
                )

        timeline += float(audio.get("duration", 0))

    caption_path.write_text("".join(lines), encoding="utf-8-sig")


def render(
    job_dir: Path,
    scene_audio: list[dict],
    visuals: list[dict],
    scenes: list[dict] | None = None,
    master_audio: dict | None = None,
) -> dict:
    render_dir = job_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    visual_clips = []

    for idx, (audio, visual) in enumerate(zip(scene_audio, visuals), start=1):
        duration = max(1.0, float(audio["duration"]))
        frames = max(1, math.ceil(duration * 30))
        clip = render_dir / f"visual_{idx:02d}.mp4"
        kind = str(visual.get("kind", ""))
        path = str(visual["path"])

        scene = (scenes or [])[idx - 1] if scenes and idx - 1 < len(scenes) else {}
        is_story_scene = bool(scene.get("game_name") or scene.get("character_visuals"))

        if kind == "ai_generated_video" or Path(path).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            framing = (
                "scale=1180:2098:force_original_aspect_ratio=increase,"
                "crop=1080:1920:(iw-1080)/2:145,"
                if is_story_scene
                else "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            )
            vf = (
                framing
                + "eq=contrast=1.05:saturation=1.08:gamma=0.99,"
                "unsharp=5:5:0.42:5:5:0.0,"
                "fps=30,format=yuv420p"
            )
            _run([
                "-stream_loop", "-1", "-i", path,
                "-t", f"{duration:.3f}",
                "-vf", vf,
                "-an",
                "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                str(clip),
            ])
        else:
            zoom_speed = 0.0010 if idx % 2 else 0.00135
            zoom_cap = 1.09 if idx % 2 else 1.12
            framing = (
                "scale=1180:2098:force_original_aspect_ratio=increase,"
                "crop=1080:1920:(iw-1080)/2:145,"
                if is_story_scene
                else "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            )
            vf = (
                framing
                + f"zoompan=z='min(zoom+{zoom_speed:.5f},{zoom_cap:.2f})':d={frames}:s=1080x1920:fps=30,"
                "eq=contrast=1.04:saturation=1.07:gamma=0.99,"
                "unsharp=5:5:0.34:5:5:0.0,"
                "format=yuv420p"
            )
            _run([
                "-loop", "1", "-i", path,
                "-t", f"{duration:.3f}",
                "-vf", vf,
                "-r", "30", "-an",
                "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                str(clip),
            ])
        visual_clips.append(clip)

    visual_list = render_dir / "visuals.txt"
    visual_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in visual_clips), encoding="utf-8")
    combined_video = render_dir / "video.mp4"
    _run(["-f", "concat", "-safe", "0", "-i", str(visual_list), "-c", "copy", str(combined_video)])

    narration = render_dir / "narration.m4a"

    if master_audio and Path(str(master_audio.get("path", ""))).exists():
        # Story mode: keep the one continuous Kokoro take intact. SFX are delayed
        # onto this master track instead of cutting/rejoining the narrator at every scene.
        voice_source = Path(str(master_audio["path"]))
        sfx_specs: list[tuple[Path, int]] = []
        timeline_ms = 0
        for idx, audio in enumerate(scene_audio):
            scene = (scenes or [])[idx] if scenes and idx < len(scenes) else {}
            sfx = pick_sfx(scene.get("sfx_cue"))
            if sfx:
                sfx_specs.append((sfx, timeline_ms + 90))
            timeline_ms += int(round(float(audio.get("duration", 0)) * 1000))

        if sfx_specs:
            args = ["-i", str(voice_source)]
            for sfx, _delay in sfx_specs:
                args.extend(["-i", str(sfx)])

            filters = ["[0:a]volume=1.0[voice]"]
            mix_labels = ["[voice]"]
            for input_idx, (_sfx, delay_ms) in enumerate(sfx_specs, start=1):
                label = f"sfx{input_idx}"
                filters.append(
                    f"[{input_idx}:a]volume=0.12,adelay={delay_ms}|{delay_ms}[{label}]"
                )
                mix_labels.append(f"[{label}]")
            filters.append(
                "".join(mix_labels)
                + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0[a]"
            )

            args.extend([
                "-filter_complex", ";".join(filters),
                "-map", "[a]",
                "-c:a", "aac", "-b:a", "192k",
                str(narration),
            ])
            _run(args)
        else:
            _run([
                "-i", str(voice_source),
                "-c:a", "aac", "-b:a", "192k",
                str(narration),
            ])
    else:
        # Legacy/non-Story path.
        mixed_scene_audio: list[Path] = []
        for idx, audio in enumerate(scene_audio):
            source = Path(audio["path"])
            scene = (scenes or [])[idx] if scenes and idx < len(scenes) else {}
            sfx = pick_sfx(scene.get("sfx_cue"))
            if not sfx:
                mixed_scene_audio.append(source)
                continue

            mixed = render_dir / f"audio_scene_{idx + 1:02d}.m4a"
            _run([
                "-i", str(source),
                "-i", str(sfx),
                "-filter_complex",
                "[0:a]volume=1.0[voice];"
                "[1:a]volume=0.16,adelay=70|70[sfx];"
                "[voice][sfx]amix=inputs=2:duration=first:dropout_transition=0[a]",
                "-map", "[a]",
                "-c:a", "aac", "-b:a", "192k",
                str(mixed),
            ])
            mixed_scene_audio.append(mixed)

        audio_list = render_dir / "audio.txt"
        audio_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in mixed_scene_audio),
            encoding="utf-8",
        )
        _run([
            "-f", "concat", "-safe", "0", "-i", str(audio_list),
            "-c:a", "aac", "-b:a", "192k",
            str(narration),
        ])

    captions = render_dir / "captions.ass"
    build_captions(scene_audio, captions, scenes=scenes)
    final_path = job_dir / "final.mp4"

    music_files = [p for p in MUSIC_DIR.glob("*.*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}]
    if music_files:
        music = random.choice(music_files)
        _run([
            "-i", str(combined_video), "-i", str(narration), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", "[1:a]volume=1.0[voice];[2:a]volume=0.085[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-vf", "ass=captions.ass",
            "-map", "0:v:0", "-map", "[a]", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(final_path),
        ], cwd=render_dir)
        music_used = str(music)
    else:
        _run([
            "-i", str(combined_video), "-i", str(narration),
            "-vf", "ass=captions.ass",
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(final_path),
        ], cwd=render_dir)
        music_used = None

    return {
        "path": str(final_path),
        "duration": round(
            float(master_audio.get("duration"))
            if master_audio and master_audio.get("duration") is not None
            else sum(float(a["duration"]) for a in scene_audio),
            2,
        ),
        "fps": 30,
        "resolution": "1080x1920",
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "music_used": music_used,
    }
