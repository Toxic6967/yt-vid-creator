from __future__ import annotations

import re
from typing import Any


ANIMATION_CLIPS: dict[str, dict[str, Any]] = {
    "idle": {"energy": 1, "description": "neutral breathing/weight shift"},
    "walk": {"energy": 2, "description": "controlled Roblox walk"},
    "run": {"energy": 4, "description": "fast Roblox run"},
    "stop": {"energy": 2, "description": "run/walk to planted stop"},
    "turn": {"energy": 2, "description": "turn to another character or threat"},
    "look_back": {"energy": 2, "description": "quick worried look over shoulder"},
    "point": {"energy": 2, "description": "point at an object/location"},
    "crouch": {"energy": 2, "description": "crouch or hide behind cover"},
    "hide": {"energy": 2, "description": "duck into cover/hiding place"},
    "jump": {"energy": 4, "description": "Roblox-style jump"},
    "stumble": {"energy": 3, "description": "short stumble/recovery"},
    "fall": {"energy": 4, "description": "game-like fall/knockback"},
    "celebrate": {"energy": 3, "description": "arms-up win reaction"},
    "react": {"energy": 2, "description": "clear surprised/scared reaction"},
    "open": {"energy": 2, "description": "reach/open/interact"},
    "push": {"energy": 3, "description": "push/button/lever interaction"},
    "pickup": {"energy": 2, "description": "bend and collect item"},
    "attack": {"energy": 4, "description": "non-graphic game attack"},
    "power_cast": {"energy": 5, "description": "controlled super-power cast"},
    "ground_slam": {"energy": 5, "description": "game-like ground slam"},
    "dash": {"energy": 5, "description": "short powered dash"},
    "shield": {"energy": 3, "description": "raise an energy shield"},
}


POWER_EFFECTS: dict[str, dict[str, Any]] = {
    "none": {"description": "no power effect"},
    "energy_orb": {
        "description": "bright contained energy gathering around one hand",
        "story_rule": "charge first, then release; cannot solve every problem instantly",
    },
    "energy_blast": {
        "description": "short non-graphic energy projectile/beam",
        "story_rule": "requires a visible wind-up and can be dodged or blocked",
    },
    "kinetic_dash": {
        "description": "fast glowing dash with a short trail",
        "story_rule": "short range only and leaves the character briefly off-balance",
    },
    "shockwave": {
        "description": "circular game-like force ring from a strike or ground slam",
        "story_rule": "close range; pushes rather than graphically injures",
    },
    "shield": {
        "description": "transparent glowing energy bubble/arc",
        "story_rule": "temporary defensive effect; movement is reduced while active",
    },
    "telekinesis": {
        "description": "small nearby Roblox props float and move",
        "story_rule": "only light nearby props, not entire buildings or players",
    },
    "portal": {
        "description": "stable circular energy portal used as a deliberate story mechanic",
        "story_rule": "must be established before the climax and cannot appear randomly",
    },
    "lightning": {
        "description": "stylized game-like electric arcs around hands/ground",
        "story_rule": "brief burst with a visible charge-up",
    },
}


CAMERA_PRESETS = {
    "wide",
    "medium",
    "close-up",
    "over-shoulder",
    "follow",
    "low-angle",
    "high-angle",
}

CAMERA_MOTIONS = {
    "static",
    "push_in",
    "pull_back",
    "track_left",
    "track_right",
    "follow",
    "small_orbit",
    "reveal_pan",
}


def power_prompt_context() -> str:
    lines = [
        "These are ORIGINAL FICTIONAL CHARACTER POWERS for animated stories. "
        "They are not claims about the real Roblox game's mechanics.",
    ]
    for key, value in POWER_EFFECTS.items():
        if key == "none":
            continue
        lines.append(
            f"- {key}: {value['description']}. Rule: {value['story_rule']}"
        )
    return "\n".join(lines)


def choose_clip_from_action(action: str, role: str = "") -> str:
    text = re.sub(r"\s+", " ", str(action or "").lower())
    checks = (
        ("ground slam", "ground_slam"),
        ("shockwave", "ground_slam"),
        ("dash", "dash"),
        ("shield", "shield"),
        ("blast", "power_cast"),
        ("energy", "power_cast"),
        ("power", "power_cast"),
        ("run", "run"),
        ("sprint", "run"),
        ("chase", "run"),
        ("escape", "run"),
        ("rush", "run"),
        ("flee", "run"),
        ("walk", "walk"),
        ("move toward", "walk"),
        ("moves toward", "walk"),
        ("approach", "walk"),
        ("head toward", "walk"),
        ("heads toward", "walk"),
        ("enter", "walk"),
        ("leave", "walk"),
        ("follow", "walk"),
        ("cross", "walk"),
        ("step", "walk"),
        ("jump", "jump"),
        ("leap", "jump"),
        ("hide", "hide"),
        ("crouch", "crouch"),
        ("duck", "crouch"),
        ("fall", "fall"),
        ("knock", "fall"),
        ("stumble", "stumble"),
        ("point", "point"),
        ("open", "open"),
        ("door", "open"),
        ("press", "push"),
        ("button", "push"),
        ("lever", "push"),
        ("pick", "pickup"),
        ("grab", "pickup"),
        ("collect", "pickup"),
        ("look back", "look_back"),
        ("looks back", "look_back"),
        ("glance back", "look_back"),
        ("watch", "turn"),
        ("look at", "turn"),
        ("looks at", "turn"),
        ("notice", "react"),
        ("spots", "react"),
        ("sees", "react"),
        ("realizes", "react"),
        ("realises", "react"),
        ("turn", "turn"),
        ("attack", "attack"),
        ("hit", "attack"),
        ("celebrate", "celebrate"),
        ("win", "celebrate"),
        ("cheer", "celebrate"),
        ("stop", "stop"),
    )
    for needle, clip in checks:
        if needle in text:
            return clip
    if role in {"hook", "reveal"}:
        return "react"
    if role == "payoff":
        return "celebrate"
    if role == "setup":
        return "turn"
    return "idle"


def choose_power_from_action(action: str) -> str:
    text = re.sub(r"\s+", " ", str(action or "").lower())
    checks = (
        ("portal", "portal"),
        ("telekin", "telekinesis"),
        ("shield", "shield"),
        ("shockwave", "shockwave"),
        ("ground slam", "shockwave"),
        ("lightning", "lightning"),
        ("electric", "lightning"),
        ("dash", "kinetic_dash"),
        ("blast", "energy_blast"),
        ("beam", "energy_blast"),
        ("energy", "energy_orb"),
        ("charge", "energy_orb"),
    )
    for needle, effect in checks:
        if needle in text:
            return effect
    return "none"


def normalise_power_effect(
    value: str | None,
    *,
    allow_powers: bool,
    action: str = "",
) -> str:
    if not allow_powers:
        return "none"
    key = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    if key in POWER_EFFECTS and key != "none":
        return key
    return choose_power_from_action(action)
