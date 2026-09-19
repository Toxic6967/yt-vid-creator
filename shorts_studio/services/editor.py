from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

import imageio_ffmpeg

from ..config import MUSIC_DIR


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


def build_captions(scene_audio: list[dict], caption_path: Path) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Main,Arial,72,&H00FFFFFF,&H0000D7FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,6,1,2,90,90,340,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    timeline = 0.0
    for scene in scene_audio:
        words = [w for w in scene.get("words", []) if w.get("text")]
        if not words:
            timeline += scene["duration"]
            continue
        for start_idx in range(0, len(words), 4):
            chunk = words[start_idx:start_idx + 4]
            start = timeline + chunk[0]["start"]
            end = timeline + chunk[-1]["start"] + max(0.18, chunk[-1]["duration"])
            phrase = " ".join(w["text"] for w in chunk)
            effect = r"{\fad(45,70)\fscx92\fscy92\t(0,120,\fscx100\fscy100)}"
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{effect}{_ass_escape(phrase)}\n"
            )
        timeline += scene["duration"]
    caption_path.write_text("".join(lines), encoding="utf-8-sig")


def render(job_dir: Path, scene_audio: list[dict], visuals: list[dict]) -> dict:
    render_dir = job_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    visual_clips = []

    for idx, (audio, visual) in enumerate(zip(scene_audio, visuals), start=1):
        duration = max(1.0, float(audio["duration"]))
        frames = max(1, math.ceil(duration * 30))
        clip = render_dir / f"visual_{idx:02d}.mp4"
        kind = str(visual.get("kind", ""))
        path = str(visual["path"])

        if kind == "ai_generated_video" or Path(path).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            vf = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
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
            vf = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
                f"zoompan=z='min(zoom+0.0012,1.10)':d={frames}:s=1080x1920:fps=30,"
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

    audio_list = render_dir / "audio.txt"
    audio_list.write_text("\n".join(f"file '{Path(a['path']).as_posix()}'" for a in scene_audio), encoding="utf-8")
    narration = render_dir / "narration.m4a"
    _run(["-f", "concat", "-safe", "0", "-i", str(audio_list), "-c:a", "aac", "-b:a", "192k", str(narration)])

    captions = render_dir / "captions.ass"
    build_captions(scene_audio, captions)
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
        "duration": round(sum(float(a["duration"]) for a in scene_audio), 2),
        "fps": 30,
        "resolution": "1080x1920",
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "music_used": music_used,
    }
