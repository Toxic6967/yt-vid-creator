from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageStat

from ..config import ROOT_DIR, settings


def _candidate_blenders() -> list[Path]:
    out: list[Path] = []
    configured = str(getattr(settings, "blender_executable", "") or "").strip()
    if configured:
        out.append(Path(configured))

    found = shutil.which("blender")
    if found:
        out.append(Path(found))

    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    foundation = program_files / "Blender Foundation"
    if foundation.exists():
        out.extend(sorted(foundation.glob("Blender */blender.exe"), reverse=True))
        out.extend(sorted(foundation.glob("Blender*/blender.exe"), reverse=True))

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if local:
        out.extend(sorted(local.glob("Programs/Blender*/blender.exe"), reverse=True))

    unique: list[Path] = []
    seen = set()
    for path in out:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def blender_executable() -> Path | None:
    for candidate in _candidate_blenders():
        if candidate.exists():
            return candidate
    return None


def health() -> dict[str, Any]:
    exe = blender_executable()
    r15 = Path(settings.roblox_r15_fbx)
    # V5 builds a deterministic segmented Roblox-style avatar directly in
    # Blender. The legacy official FBX is still reported for compatibility, but
    # it is no longer allowed to block rendering when an FBX import behaves
    # differently across Blender versions.
    ready = bool(exe)
    return {
        "ready": ready,
        "backend": "blender_roblox_machinima_v5",
        "executable": str(exe) if exe else None,
        "procedural_avatar_ready": bool(exe),
        "official_r15_ready": r15.exists() and r15.stat().st_size >= 100_000 if r15.exists() else False,
        "official_r15_path": str(r15),
        "install_hint": "Run install_animation_engine.bat" if not ready else None,
    }


def _validate_rendered_clip(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "file missing"
    size = path.stat().st_size
    if size < 4096:
        return False, f"file too small ({size} bytes)"

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-frames:v",
            "3",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode != 0:
        return False, (probe.stderr or probe.stdout or "FFmpeg could not decode the clip")[-900:]
    return True, "ok"


def _encode_frame_sequence(report: dict[str, Any], clip: Path) -> None:
    frames_dir = Path(str(report.get("frames_dir") or ""))
    pattern = str(report.get("frame_pattern") or "frame_%04d.jpg")
    fps = int(report.get("fps") or 24)
    frame_count = int(report.get("rendered_frame_count") or report.get("frames") or 0)

    if not frames_dir.exists():
        raise RuntimeError(f"Blender frame directory is missing: {frames_dir}")

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError(f"Blender rendered no JPEG frames in {frames_dir}")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "1",
        "-i",
        str(frames_dir / pattern),
    ]
    if frame_count > 0:
        command.extend(["-frames:v", str(frame_count)])
    command.extend(
        [
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(clip),
        ]
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60 * 60,
    )
    if result.returncode != 0 or not clip.exists():
        raise RuntimeError(
            "FFmpeg could not encode the Blender frame sequence: "
            + (result.stderr or result.stdout or "unknown FFmpeg error")[-1600:]
        )


def _sample_visual_quality(
    path: Path,
    sample_dir: Path,
    *,
    expected_motion: bool,
) -> dict[str, Any]:
    sample_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    first = sample_dir / (path.stem + "_first.png")
    last = sample_dir / (path.stem + "_last.png")

    commands = (
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", "0.15", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=180:-2", str(first),
        ],
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-sseof", "-0.20", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=180:-2", str(last),
        ],
    )
    try:
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return {
                    "passed": False,
                    "reason": (result.stderr or result.stdout or "frame sample failed")[-700:],
                }

        with Image.open(first) as first_image, Image.open(last) as last_image:
            a = first_image.convert("L")
            b = last_image.convert("L")
            brightness = (
                float(ImageStat.Stat(a).mean[0])
                + float(ImageStat.Stat(b).mean[0])
            ) / (2.0 * 255.0)
            difference = ImageChops.difference(a, b)
            motion_score = float(ImageStat.Stat(difference).mean[0]) / 255.0

        brightness_ok = 0.015 <= brightness <= 0.985
        motion_ok = (motion_score >= 0.0025) if expected_motion else True
        return {
            "passed": bool(brightness_ok and motion_ok),
            "brightness": round(brightness, 4),
            "motion_score": round(motion_score, 4),
            "brightness_ok": brightness_ok,
            "motion_ok": motion_ok,
            "expected_motion": expected_motion,
        }
    except Exception as exc:
        return {"passed": False, "reason": str(exc)}
    finally:
        for sample in (first, last):
            try:
                sample.unlink(missing_ok=True)
            except Exception:
                pass


def render_animation_plan(
    plan: dict[str, Any],
    job_dir: Path,
) -> list[dict[str, Any]]:
    exe = blender_executable()
    if not exe:
        raise RuntimeError(
            "The V5 Roblox machinima engine needs Blender. "
            "Run install_animation_engine.bat, then restart Shorts Studio."
        )

    animation_dir = job_dir / "animation"
    clips_dir = animation_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    plan_path = animation_dir / "animation_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    script = ROOT_DIR / "scripts" / "blender" / "render_story_v5.py"
    if not script.exists():
        raise RuntimeError(f"Blender Story renderer is missing: {script}")

    command = [
        str(exe),
        "--background",
        "--factory-startup",
        "--python",
        str(script),
        "--",
        "--plan",
        str(plan_path),
        "--output-dir",
        str(clips_dir),
        "--r15-template",
        str(Path(settings.roblox_r15_fbx)),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60 * 60 * 3,
    )
    log = animation_dir / "blender.log"
    combined_output = (result.stdout or "") + "\n--- STDERR ---\n" + (result.stderr or "")
    log.write_text(
        combined_output,
        encoding="utf-8",
        errors="replace",
    )

    # Blender can print an uncaught Python traceback from --python while the
    # outer Blender process still exits without a useful non-zero status.
    # Detect the script crash directly so we report the real error instead of
    # falling through to a confusing "video file missing" validation failure.
    python_crashed = (
        "Traceback (most recent call last):" in combined_output
        or "AttributeError:" in combined_output
        or "NameError:" in combined_output
        or "SyntaxError:" in combined_output
        or "TypeError:" in combined_output
        or "RuntimeError:" in combined_output
    )
    if result.returncode != 0 or python_crashed:
        tail = combined_output[-2400:]
        raise RuntimeError(
            "Blender animation script crashed before a scene video was completed. "
            f"See {log}. Blender output tail: {tail}"
        )

    visuals: list[dict[str, Any]] = []
    for shot in plan.get("shots") or []:
        index = int(shot.get("index", len(visuals))) + 1
        clip = clips_dir / f"scene_{index:02d}.mp4"
        report_path = clips_dir / f"scene_{index:02d}.json"
        render_report: dict[str, Any] = {}
        if report_path.exists():
            try:
                render_report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                render_report = {}

        # Blender 5 renders frame sequences; encode them with the app's tested
        # FFmpeg binary before running the normal clip validators.
        if not clip.exists() and render_report.get("frames_dir"):
            _encode_frame_sequence(render_report, clip)

        valid, reason = _validate_rendered_clip(clip)
        if not valid:
            files = ", ".join(
                f"{path.name} ({path.stat().st_size} bytes)"
                for path in sorted(clips_dir.glob("*"))
                if path.is_file()
            )
            report = ""
            if report_path.exists():
                try:
                    report = report_path.read_text(encoding="utf-8")[-1600:]
                except Exception:
                    report = ""
            log_tail = ""
            try:
                log_tail = log.read_text(encoding="utf-8", errors="replace")[-1800:]
            except Exception:
                pass
            raise RuntimeError(
                f"Blender scene {index} did not pass video validation: {reason}. "
                f"Files: {files or 'none'}. "
                + (f"Scene report: {report}. " if report else "")
                + (f"Blender log tail: {log_tail}" if log_tail else "")
            )

        actor_clips = {
            str(actor.get("clip") or "idle")
            for actor in (shot.get("actors") or [])
        }
        strong_motion = {
            "walk", "run", "dash", "jump", "stumble", "fall", "attack",
            "power_cast", "ground_slam", "celebrate",
        }
        expected_motion = (
            bool(actor_clips & strong_motion)
            or str(shot.get("camera_motion") or "static") != "static"
            or any(
                actor.get("power_effect") not in {None, "", "none"}
                for actor in (shot.get("actors") or [])
            )
        )
        visual_quality = _sample_visual_quality(
            clip,
            animation_dir / "validation",
            expected_motion=expected_motion,
        )
        if not visual_quality.get("passed"):
            raise RuntimeError(
                f"Blender scene {index} rendered, but visual validation rejected it: "
                f"{json.dumps(visual_quality, ensure_ascii=False)}"
            )

        frames_dir_value = render_report.get("frames_dir")
        if frames_dir_value:
            try:
                shutil.rmtree(Path(str(frames_dir_value)), ignore_errors=True)
            except Exception:
                pass

        visuals.append(
            {
                "path": str(clip),
                "kind": "blender_animated_scene",
                "backend": "blender_roblox_machinima_v5",
                "query": shot.get("action") or "",
                "animation_clip_count": len(shot.get("actors") or []),
                "camera": shot.get("camera"),
                "camera_motion": shot.get("camera_motion"),
                "power_effects": [
                    actor.get("power_effect")
                    for actor in (shot.get("actors") or [])
                    if actor.get("power_effect") not in {None, "", "none"}
                ],
                "render_report": render_report,
                "visual_quality": visual_quality,
                "validated_video": True,
            }
        )
    return visuals
