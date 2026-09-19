from __future__ import annotations

from typing import Any

from ..db import get_channel_profile
from .ollama_client import chat_json

IMAGE_STYLES = {
    "roblox_bright": "bright polished Roblox-inspired game scene, colourful, readable shapes, playful depth, energetic lighting",
    "roblox_cinematic": "cinematic Roblox-inspired game scene, dramatic composition, volumetric light, polished game-render look",
    "thumbnail": "high-impact YouTube gaming thumbnail composition, clear single subject, bold depth, expressive action, clean background separation",
    "gameplay": "authentic-looking Roblox-style gameplay scene, third-person game camera, readable environment, energetic action",
    "clean_3d": "clean stylised 3D game render, simple forms, strong silhouette, vibrant lighting",
}

VIDEO_STYLES = {
    "roblox_bright": "bright Roblox-inspired 3D game animation, energetic but readable, colourful polished environment",
    "roblox_cinematic": "cinematic Roblox-inspired 3D game animation, dramatic lighting, strong subject focus",
    "gameplay": "Roblox-style third-person gameplay shot, believable game camera, responsive character movement",
    "reveal": "fast gaming reveal shot with clear anticipation then payoff, polished Roblox-inspired 3D style",
}

CAMERA_MOVES = {
    "auto": "choose one simple camera move that best supports the action",
    "push_in": "smooth fast push-in toward the subject",
    "orbit": "small cinematic orbit around the subject",
    "follow": "third-person follow camera tracking the subject",
    "pan": "quick controlled pan revealing the important object",
    "static": "mostly locked camera with subject motion doing the work",
}


def _profile() -> dict[str, Any]:
    p = get_channel_profile()
    return {
        "niche": p.get("niche", "Roblox"),
        "tone": p.get("tone", "Fast Roblox gaming documentary"),
        "audience": p.get(
            "audience",
            "Kids / young Roblox players (roughly 8-14); energetic, clear, exciting, never babyish",
        ),
    }


def enhance_image_prompt(
    prompt: str,
    *,
    style: str = "roblox_bright",
    purpose: str = "scene_visual",
) -> dict[str, str]:
    profile = _profile()
    style_text = IMAGE_STYLES.get(style, IMAGE_STYLES["roblox_bright"])
    try:
        result = chat_json(
            "You are the visual director for a high-quality Roblox YouTube Shorts channel. Return JSON only.",
            f"""
AUDIENCE: {profile['audience']}
CHANNEL TONE: {profile['tone']}
PURPOSE: {purpose}
STYLE: {style_text}
USER IDEA: {prompt}

Turn the idea into one precise image-generation prompt.

Rules:
- The image must visibly represent the idea, not just be a generic gaming background.
- Make the focal subject obvious in under one second.
- Design for a young Roblox audience: colourful, exciting and easy to read, but never babyish.
- Prefer one strong action or reveal over clutter.
- Use game-like environments, expressive posing and clear depth.
- No logos, watermarks, UI text, captions, typography or random written words.
- Do not add unrelated objects just to make it look busy.
- If the idea contains a named real Roblox experience, describe its recognizable type of setting/action without pretending an exact copyrighted screenshot was generated.
- Output should be suitable for vertical Shorts unless the user chose another aspect.

Return:
{{"prompt":"...", "negative_prompt":"..."}}
""",
            temperature=0.35,
        )
        return {
            "prompt": str(result.get("prompt") or prompt).strip(),
            "negative_prompt": str(
                result.get("negative_prompt")
                or "text, logo, watermark, blurry, low detail, broken anatomy, duplicated objects, cluttered composition"
            ).strip(),
        }
    except Exception:
        return {
            "prompt": f"{prompt}, {style_text}, clear focal subject, energetic young gaming audience, polished 3D game render, no text",
            "negative_prompt": "text, logo, watermark, blurry, low quality, clutter, duplicated objects, broken anatomy",
        }


def enhance_video_prompt(
    prompt: str,
    *,
    style: str = "roblox_bright",
    camera: str = "auto",
    purpose: str = "b_roll",
    seconds: int = 5,
) -> dict[str, str]:
    profile = _profile()
    style_text = VIDEO_STYLES.get(style, VIDEO_STYLES["roblox_bright"])
    camera_text = CAMERA_MOVES.get(camera, CAMERA_MOVES["auto"])
    try:
        result = chat_json(
            "You are the shot director for a fast, high-retention Roblox YouTube Shorts channel. Return JSON only.",
            f"""
AUDIENCE: {profile['audience']}
CHANNEL TONE: {profile['tone']}
CLIP PURPOSE: {purpose}
CLIP LENGTH: {seconds} seconds
STYLE: {style_text}
CAMERA: {camera_text}
USER IDEA: {prompt}

Write one prompt for a genuine text-to-video model.

Rules:
- Describe ONE clear shot that can actually happen in {seconds} seconds.
- The first frame should already contain something interesting.
- Motion must have a beginning and a visible payoff by the final frame.
- Keep the subject consistent; avoid morphing into unrelated objects.
- Use one clear camera move, not five camera moves at once.
- Make it readable for a young Roblox audience: exciting and colourful, but not preschool-like.
- No text, logos, captions, watermarks, fake UI or random letters.
- Do not ask the model to create a full multi-scene Short; this is one reusable shot.

Return:
{{"prompt":"...", "negative_prompt":"..."}}
""",
            temperature=0.35,
        )
        return {
            "prompt": str(result.get("prompt") or prompt).strip(),
            "negative_prompt": str(
                result.get("negative_prompt")
                or "text, logo, watermark, flicker, morphing, distorted body, duplicate character, blurry, low quality"
            ).strip(),
        }
    except Exception:
        return {
            "prompt": f"{prompt}. {style_text}. {camera_text}. One clear action with a visible payoff, no text.",
            "negative_prompt": "text, logo, watermark, flicker, morphing, duplicate character, distorted anatomy, blur",
        }


def scene_image_prompt(scene: dict, topic: str) -> str:
    if scene.get("keyframe_prompt"):
        return str(scene["keyframe_prompt"]).strip()

    narration = str(scene.get("narration", "")).strip()
    query = str(scene.get("visual_query", "")).strip()
    emphasis = str(scene.get("on_screen_emphasis", "")).strip()
    character_visuals = "; ".join(str(x) for x in scene.get("character_visuals", []) if x)
    environment = str(scene.get("environment", "")).strip()
    action = str(scene.get("action", "")).strip()
    camera = str(scene.get("camera", "")).strip()

    details = []
    if character_visuals:
        details.append(f"Characters must match exactly: {character_visuals}")
    if environment:
        details.append(f"Environment: {environment}")
    if action:
        details.append(f"Action: {action}")
    if camera:
        details.append(f"Camera: {camera}")

    return (
        f"Scene topic: {topic}. Narration meaning: {narration}. "
        f"Show visually: {query or narration}. Important idea: {emphasis}. "
        + ". ".join(details)
        + ". Create a polished modern Roblox-style cinematic frame that directly illustrates this exact beat."
    )


def scene_video_prompt(scene: dict, topic: str) -> str:
    if scene.get("motion_prompt"):
        base = str(scene["motion_prompt"]).strip()
    else:
        base = scene_image_prompt(scene, topic)

    character_visuals = "; ".join(str(x) for x in scene.get("character_visuals", []) if x)
    environment = str(scene.get("environment", "")).strip()
    action = str(scene.get("action", "")).strip()
    camera = str(scene.get("camera", "")).strip()

    return (
        f"{base} "
        f"Characters: {character_visuals}. "
        f"Environment: {environment}. "
        f"Action over time: {action}. "
        f"Camera: {camera}. "
        "Modern polished Roblox-style 3D movie shot, cinematic lighting, clean materials, strong depth, "
        "natural blocky character motion, consistent faces/clothes/hair, no morphing, no random costume changes."
    )
