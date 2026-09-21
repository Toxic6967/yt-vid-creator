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
    power_rules = ((script.get("game_context") or {}).get("power_rules") or {})
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
            action_context = " ".join(
                str(value or "")
                for value in (
                    scene.get("action"),
                    scene.get("narration"),
                    scene.get("emotion"),
                    scene.get("changes"),
                )
            )
            actor_name = str(characters[cid].get("name") or cid)
            lower_context = action_context.lower()
            actor_is_named = (
                cid in lower_context
                or actor_name.lower() in lower_context
                or len(visible) == 1
            )
            inferred_clip = (
                choose_clip_from_action(
                    action_context,
                    str(scene.get("role") or ""),
                )
                if actor_is_named
                else ("react" if str(scene.get("role") or "") in {"hook", "reveal"} else "idle")
            )
            if clip not in ANIMATION_CLIPS:
                clip = inferred_clip
            elif clip == "idle" and inferred_clip != "idle":
                clip = inferred_clip

            try:
                start_lane = float(proposed.get("start_lane", lanes[actor_index]))
            except Exception:
                start_lane = float(lanes[actor_index])
            try:
                end_lane = float(proposed.get("end_lane", start_lane))
            except Exception:
                end_lane = start_lane

            # Locomotion should actually cross screen instead of running in place
            # when the planner omits lane movement.
            if abs(end_lane - start_lane) < 0.15 and clip in {"walk", "run", "dash"}:
                direction = -1.0 if actor_index % 2 else 1.0
                travel = 0.8 if clip == "walk" else (1.25 if clip == "run" else 1.65)
                end_lane = start_lane + direction * travel

            power_effect = normalise_power_effect(
                proposed.get("power_effect"),
                allow_powers=allow_powers,
                action=(action_context if actor_is_named else ""),
            )
            allowed_for_character = {
                str(x).lower()
                for x in ((power_rules.get(cid) or {}).get("abilities") or [])
            }
            if allowed_for_character and power_effect not in allowed_for_character:
                # Keep special effects character/mechanic-specific when a
                # verified game context supplies an explicit ability list.
                power_effect = "none"

            actors.append(
                {
                    "id": cid,
                    "name": characters[cid].get("name") or cid.title(),
                    "visual_identity": characters[cid].get("visual_identity") or "",
                    "emotion": str(scene.get("emotion") or ""),
                    "clip": clip,
                    "start_lane": _clamp(start_lane, -2.4, 2.4),
                    "end_lane": _clamp(end_lane, -2.4, 2.4),
                    "facing": "left" if str(proposed.get("facing")).lower() == "left" else "right",
                    "power_effect": power_effect,
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

    # Deterministic repair: never throw away an otherwise good Story because
    # the animation LLM was too conservative. Make the PRIMARY actor perform a
    # readable non-idle beat on enough shots, using only generic body acting
    # when the screenplay did not name a more specific action.
    required_active = max(6, round(len(shots) * 0.76))
    active_now = sum(
        1
        for shot in shots
        if any(actor.get("clip") != "idle" for actor in (shot.get("actors") or []))
    )
    if active_now < required_active:
        generic_cycle = ("react", "turn", "look_back")
        for idx, shot in enumerate(shots):
            if active_now >= required_active:
                break
            actors = shot.get("actors") or []
            if not actors:
                continue
            if any(actor.get("clip") != "idle" for actor in actors):
                continue

            role = str(shot.get("role") or "")
            context = " ".join(
                str(value or "")
                for value in (
                    shot.get("action"),
                    shot.get("emotion"),
                )
            )
            inferred = choose_clip_from_action(context, role)
            if inferred == "idle":
                if role == "payoff":
                    inferred = "celebrate"
                elif role in {"hook", "reveal"}:
                    inferred = "react"
                else:
                    inferred = generic_cycle[idx % len(generic_cycle)]

            actors[0]["clip"] = inferred
            active_now += 1

    # Repair repeated camera language before checking static shots. Even when a
    # story revisits one location, consecutive cuts should reveal it differently
    # instead of looking like the same background with another zoom.
    camera_cycle = ("wide", "medium", "close-up", "over-shoulder", "follow", "low-angle", "high-angle")
    motion_cycle_all = ("track_left", "track_right", "follow", "small_orbit", "reveal_pan", "push_in")
    for idx in range(1, len(shots)):
        prev = shots[idx - 1]
        shot = shots[idx]
        same_environment = str(prev.get("environment_key") or "") == str(shot.get("environment_key") or "")
        same_combo = (
            str(prev.get("camera") or "") == str(shot.get("camera") or "")
            and str(prev.get("camera_motion") or "") == str(shot.get("camera_motion") or "")
        )
        if same_environment and same_combo:
            shot["camera"] = camera_cycle[(idx + 2) % len(camera_cycle)]
            shot["camera_motion"] = motion_cycle_all[(idx + 1) % len(motion_cycle_all)]

    # Repair an overly static camera plan as well. The shot's framing remains
    # locked; only a deliberate camera move is added.
    max_static = max(3, round(len(shots) * 0.48))
    static_indexes = [
        idx for idx, shot in enumerate(shots)
        if str(shot.get("camera_motion") or "static") == "static"
    ]
    if len(static_indexes) > max_static:
        motion_cycle = ("push_in", "track_left", "track_right", "small_orbit", "reveal_pan")
        repair_count = len(static_indexes) - max_static
        for repair_index, shot_index in enumerate(static_indexes[:repair_count]):
            shot = shots[shot_index]
            if str(shot.get("camera") or "") == "follow":
                shot["camera_motion"] = "follow"
            else:
                shot["camera_motion"] = motion_cycle[
                    (shot_index + repair_index) % len(motion_cycle)
                ]

    return {
        "version": "v5.2",
        "render_style": "roblox_3d_machinima",
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
    if animated < max(6, round(len(shots) * 0.72)):
        problems.append("Too many shots use only idle poses.")

    static_cameras = sum(
        1 for shot in shots
        if str(shot.get("camera_motion") or "static") == "static"
    )
    repeated_same_environment_combo = sum(
        1
        for idx in range(1, len(shots))
        if str(shots[idx - 1].get("environment_key") or "") == str(shots[idx].get("environment_key") or "")
        and str(shots[idx - 1].get("camera") or "") == str(shots[idx].get("camera") or "")
        and str(shots[idx - 1].get("camera_motion") or "") == str(shots[idx].get("camera_motion") or "")
    )
    if static_cameras > max(3, round(len(shots) * 0.45)):
        problems.append("Too many shots use a completely static camera.")
    if repeated_same_environment_combo:
        problems.append("Repeated location shots reuse the exact same camera language.")

    if plan.get("allow_powers") and powered < 2:
        problems.append("Power-story mode needs at least two visible, story-motivated power VFX beats.")

    return {
        "passed": not problems,
        "shot_count": len(shots),
        "camera_count": len(cameras),
        "environment_count": len(environments),
        "active_motion_shots": animated,
        "static_camera_shots": static_cameras,
        "repeated_same_environment_camera_combos": repeated_same_environment_combo,
        "power_effect_shots": powered,
        "problems": problems,
    }
