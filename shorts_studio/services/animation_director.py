from __future__ import annotations

from pathlib import Path
from typing import Any

from .blender_bridge import health as blender_health, render_animation_plan
from .shot_planner import build_animation_plan


def render_animated_story(
    *,
    script: dict[str, Any],
    scene_audio: list[dict[str, Any]],
    environment_plates: dict[str, str],
    job_dir: Path,
) -> dict[str, Any]:
    state = blender_health()
    if not state.get("ready"):
        raise RuntimeError(
            "V5 Roblox machinima animation is selected, but Blender is not installed. "
            "Run install_animation_engine.bat, restart Shorts Studio, then regenerate."
        )

    plan = build_animation_plan(script, scene_audio, environment_plates)
    quality = plan.get("quality") or {}
    if not quality.get("passed"):
        raise RuntimeError(
            "Animation director rejected its own shot plan: "
            + "; ".join(str(x) for x in (quality.get("problems") or []))
        )

    visuals = render_animation_plan(plan, job_dir)
    if len(visuals) != len(script.get("scenes") or []):
        raise RuntimeError(
            f"Animation engine returned {len(visuals)} clips for "
            f"{len(script.get('scenes') or [])} story scenes."
        )

    return {
        "engine": state,
        "plan": plan,
        "quality": quality,
        "visuals": visuals,
    }
