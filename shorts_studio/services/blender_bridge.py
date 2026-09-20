from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

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
    return {
        "ready": bool(exe),
        "backend": "blender_r15_v3",
        "executable": str(exe) if exe else None,
        "install_hint": "Run install_animation_engine.bat" if not exe else None,
    }


def render_animation_plan(
    plan: dict[str, Any],
    job_dir: Path,
) -> list[dict[str, Any]]:
    exe = blender_executable()
    if not exe:
        raise RuntimeError(
            "The V3 Roblox animation engine needs Blender. "
            "Run install_animation_engine.bat, then restart Shorts Studio."
        )

    animation_dir = job_dir / "animation"
    clips_dir = animation_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    plan_path = animation_dir / "animation_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    script = ROOT_DIR / "scripts" / "blender" / "render_story.py"
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
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60 * 60 * 3,
    )
    log = animation_dir / "blender.log"
    log.write_text(
        (result.stdout or "") + "\n--- STDERR ---\n" + (result.stderr or ""),
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Blender animation render failed. "
            f"See {log}. Last output: {(result.stderr or result.stdout or '')[-1200:]}"
        )

    visuals: list[dict[str, Any]] = []
    for shot in plan.get("shots") or []:
        index = int(shot.get("index", len(visuals))) + 1
        clip = clips_dir / f"scene_{index:02d}.mp4"
        if not clip.exists() or clip.stat().st_size < 10_000:
            raise RuntimeError(f"Blender did not produce a usable clip for scene {index}.")
        visuals.append(
            {
                "path": str(clip),
                "kind": "blender_animated_scene",
                "backend": "blender_r15_v3",
                "query": shot.get("action") or "",
                "animation_clip_count": len(shot.get("actors") or []),
                "camera": shot.get("camera"),
                "camera_motion": shot.get("camera_motion"),
                "power_effects": [
                    actor.get("power_effect")
                    for actor in (shot.get("actors") or [])
                    if actor.get("power_effect") not in {None, "", "none"}
                ],
            }
        )
    return visuals
