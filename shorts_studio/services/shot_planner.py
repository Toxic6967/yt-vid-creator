from __future__ import annotations

import json
from typing import Any

from .animation_timeline import animation_plan_quality, normalise_animation_plan
from .asset_registry import (
    ANIMATION_CLIPS,
    CAMERA_MOTIONS,
    CAMERA_PRESETS,
    POWER_EFFECTS,
)
from .ollama_client import chat_json


def build_animation_plan(
    script: dict[str, Any],
    scene_audio: list[dict[str, Any]],
    environment_plates: dict[str, str],
) -> dict[str, Any]:
    scenes = script.get("scenes") or []
    allow_powers = str(script.get("genre") or "").lower() == "powers"

    compact = [
        {
            "index": idx,
            "role": scene.get("role"),
            "narration": scene.get("narration"),
            "action": scene.get("action"),
            "emotion": scene.get("emotion"),
            "characters": scene.get("characters") or [],
            "environment": scene.get("environment"),
            "camera": scene.get("camera"),
            "duration": (
                float(scene_audio[idx].get("duration") or 3.0)
                if idx < len(scene_audio)
                else 3.0
            ),
        }
        for idx, scene in enumerate(scenes)
    ]

    prompt = f"""
You are directing CONTROLLED Roblox R15 animation, not generative video.

STORY SHOTS:
{json.dumps(compact, ensure_ascii=False)}

AVAILABLE ANIMATION CLIPS:
{json.dumps(sorted(ANIMATION_CLIPS.keys()))}

AVAILABLE CAMERA FRAMINGS:
{json.dumps(sorted(CAMERA_PRESETS))}

AVAILABLE CAMERA MOTIONS:
{json.dumps(sorted(CAMERA_MOTIONS))}

POWERS ALLOWED: {allow_powers}
AVAILABLE POWER EFFECTS:
{json.dumps(sorted(POWER_EFFECTS.keys()))}

Plan movement only. Do not rewrite plot, narration, environments or character identities.

Rules:
- Return exactly {len(scenes)} shots, indexes 0..{max(0, len(scenes)-1)}.
- Use the characters already listed for each shot.
- One primary readable animation per visible character.
- Every animation must physically match the CURRENT scene action and CURRENT verified game environment. Do not invent travel, combat, doors, vehicles or props that the screenplay did not establish.
- Prefer interactions that make the researched Roblox game readable on screen: run only when the action says run/chase/escape, jump for an actual obstacle, open for an established door/container, push for a real button/lever, pickup for an established item, and react/turn/point for dialogue or discovery.
- Prefer Roblox-like movement: run, jump, crouch, point, react, open, push, pickup, fall, celebrate.
- Keep positions within lanes -2.4 to +2.4.
- start_lane/end_lane are screen-space staging positions, not game coordinates.
- Use camera movement deliberately; characters must stay readable on a phone.
- Prefer a subtle push, follow, track, reveal or orbit on important beats rather than freezing the camera.
- Avoid every shot being centered/medium/static.
- Do not repeat the same camera + motion combination more than twice in a row.
- Running/walking/dashing actors should visibly travel across the staging lanes instead of running in place.
- Reactions should use head/torso acting, not only arm movement.
- Keep actors staged on the floor and readable against the environment; do not plan floating/flying movement unless the screenplay explicitly requires it.
- Use close-up/medium shots for discoveries and interactions, follow/wide shots for real movement, and avoid cutting to an unrelated generic location just to create variety.
- If POWERS ALLOWED is false, every power_effect must be "none".
- If POWERS ALLOWED is true, use power effects only where the existing action/story clearly calls for one, but make sure the story contains at least two visible power-effect beats so the genre actually feels special.
- Powers are stylized non-graphic VFX, not realistic violence.
- Never add a new event just because an effect would look cool.

Return:
{{
  "shots":[
    {{
      "index":0,
      "camera":"wide|medium|close-up|over-shoulder|follow|low-angle|high-angle",
      "camera_motion":"static|push_in|pull_back|track_left|track_right|follow|small_orbit|reveal_pan",
      "actors":[
        {{
          "id":"existing character id",
          "clip":"one allowed animation clip",
          "start_lane":0.0,
          "end_lane":0.0,
          "facing":"left|right",
          "power_effect":"one allowed power effect"
        }}
      ]
    }}
  ]
}}
"""

    try:
        raw = chat_json(
            "You are a technical animation director. Return compact JSON only.",
            prompt,
            temperature=0.18,
        )
    except Exception:
        raw = {"shots": []}

    plan = normalise_animation_plan(
        raw,
        script=script,
        scene_audio=scene_audio,
        environment_plates=environment_plates,
        allow_powers=allow_powers,
    )
    plan["quality"] = animation_plan_quality(plan)
    return plan
