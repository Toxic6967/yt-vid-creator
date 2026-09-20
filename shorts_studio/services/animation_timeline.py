from __future__ import annotations

import re
from typing import Any

from .asset_registry import (
    ANIMATION_CLIPS,
    CAMERA_MOTIONS,
    CAMERA_PRESETS,
    choose_clip_from_action,
    normalise_power_effect,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalise_animation_plan(
    raw: dict[str, Any],
    *,
    script: dict[str, Any],
    scene_audio: list[dict[str, Any]],
    environment_plates: dict[str, str],
    allow_powers: bool,
) -> dict[str, Any]:
    scenes = script.get("scenes") or []
    raw_shots = raw.get("shots") if isinstance(raw.get("shots"), list) else []
    by_index: dict[int, dict[str, Any]] = {}
    for item in raw_shots:
        if not isinstance(item, dict):
            continue
        try:
            by_index[int(item.get("index"))] = item
        except Exception:
            continue

    characters = {
        str(item.get("id") or "").lower(): item
        for item in (script.get("characters") or [])
        if item.get("id")
    }
    shots: list[dict[str, Any]] = []

    for idx, scene in enumerate(scenes):
        raw_shot = by_index.get(idx, {})
        duration = (
            float(scene_audio[idx].get("duration") or 3.0)
            if idx < len(scene_audio)
            else 3.0
        )
        duration = _clamp(duration, 1.3, 6.5)

        environment_key = re.sub(
            r"\s+",
            " ",
            str(
                scene.get("environment_key")
                or scene.get("environment")
                or f"scene-{idx + 1}"
            ).strip().lower(),
        )
        background = environment_plates.get(environment_key)

        camera = str(raw_shot.get("camera") or scene.get("camera") or "medium").lower()
        if camera not in CAMERA_PRESETS:
            camera = "medium"
        camera_motion = str(raw_shot.get("camera_motion") or "").lower()
        if camera_motion not in CAMERA_MOTIONS:
            camera_motion = (
                "push_in" if str(scene.get("role") or "") in {"hook", "reveal"}
                else "follow" if camera == "follow"
                else "static"
            )

        visible = [
            str(value).lower()
            for value in (scene.get("characters") or [])
            if str(value).lower() in characters
        ]
        if not visible and characters:
            visible = [next(iter(characters))]

        raw_actors = raw_shot.get("actors") if isinstance(raw_shot.get("actors"), list) else []
        actor_by_id = {
            str(item.get("id") or "").lower(): item
            for item in raw_actors
            if isinstance(item, dict) and item.get("id")
        }

        lanes = {
            1: [0.0],
            2: [-1.25, 1.25],
            3: [-1.85, 0.0, 1.85],
        }.get(len(visible), [0.0])

        actors: list[dict[str, Any]] = []
        for actor_index, cid in enumerate(visible[:3]):
            proposed = actor_by_id.get(cid, {})
            clip = str(proposed.get("clip") or "").lower()
            if clip not in ANIMATION_CLIPS:
                clip = choose_clip_from_action(
                    str(scene.get("action") or ""),
                    str(scene.get("role") or ""),
                )

            start_lane = float(proposed.get("start_lane", lanes[actor_index]))
            end_lane = float(proposed.get("end_lane", start_lane))
            actors.append(
                {
                    "id": cid,
                    "name": characters[cid].get("name") or cid.title(),
                    "visual_identity": characters[cid].get("visual_identity") or "",
                    "clip": clip,
                    "start_lane": _clamp(start_lane, -2.4, 2.4),
                    "end_lane": _clamp(end_lane, -2.4, 2.4),
                    "facing": "left" if str(proposed.get("facing")).lower() == "left" else "right",
                    "power_effect": normalise_power_effect(
                        proposed.get("power_effect"),
                        allow_powers=allow_powers,
                    ),
                }
            )

        shots.append(
            {
                "index": idx,
                "role": scene.get("role") or "build",
                "duration": round(duration, 3),
                "environment_key": environment_key,
                "environment": scene.get("environment") or environment_key,
                "background_path": background,
                "action": scene.get("action") or "",
                "emotion": scene.get("emotion") or "",
                "camera": camera,
                "camera_motion": camera_motion,
                "actors": actors,
            }
        )

    return {
        "version": "v3.0",
        "render_style": "roblox_r15_animation",
        "game_name": script.get("game_name") or "Roblox",
        "genre": script.get("genre") or "relatable",
        "allow_powers": allow_powers,
        "shots": shots,
    }


def animation_plan_quality(plan: dict[str, Any]) -> dict[str, Any]:
    shots = plan.get("shots") or []
    if not shots:
        return {"passed": False, "problems": ["No animation shots were planned."]}

    cameras = {str(s.get("camera") or "") for s in shots}
    environments = {str(s.get("environment_key") or "") for s in shots}
    animated = sum(1 for s in shots if any(a.get("clip") != "idle" for a in (s.get("actors") or [])))
    powered = sum(
        1
        for s in shots
        if any(a.get("power_effect") not in {None, "", "none"} for a in (s.get("actors") or []))
    )
    problems = []
    if len(cameras) < 4:
        problems.append("Animation plan does not vary camera framing enough.")
    if len(environments) < 4:
        problems.append("Animation plan does not use enough distinct game areas.")
    if animated < max(6, round(len(shots) * 0.65)):
        problems.append("Too many shots use only idle poses.")

    return {
        "passed": not problems,
        "shot_count": len(shots),
        "camera_count": len(cameras),
        "environment_count": len(environments),
        "active_motion_shots": animated,
        "power_effect_shots": powered,
        "problems": problems,
    }
