from __future__ import annotations

import html
import random
import re
import zlib
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import settings
from .comfyui_client import (
    generate_ai_image,
    generate_ai_image_from_reference,
    generate_ai_video,
    generate_story_keyframe,
    generate_story_video_from_image,
    health as comfyui_health,
)
from .media_director import (
    enhance_image_prompt,
    enhance_video_prompt,
    scene_image_prompt,
    scene_video_prompt,
)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSE_MARKERS = ("cc by", "cc-by", "cc by-sa", "cc-by-sa", "cc0", "public domain", "pd-")


def _strip_html(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _license_allowed(name: str) -> bool:
    key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    if "public domain" in key or key.startswith("pd ") or key == "pd" or "cc0" in key:
        return True
    if "cc by" in key and all(blocked not in key for blocked in (" by sa", " nc", " nd")):
        return True
    return False


def _font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def search_commons(query: str) -> dict[str, Any] | None:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 10,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 1600,
        "origin": "*",
    }
    headers = {"User-Agent": settings.user_agent}
    try:
        with httpx.Client(timeout=12, headers=headers) as client:
            response = client.get(COMMONS_API, params=params)
            response.raise_for_status()
            pages = (response.json().get("query") or {}).get("pages", {})
    except Exception:
        return None

    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime", "")
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
        if not _license_allowed(license_name):
            continue
        return {
            "title": page.get("title", ""),
            "download_url": info.get("thumburl") or info.get("url"),
            "source_url": info.get("descriptionurl") or info.get("url"),
            "author": _strip_html((meta.get("Artist") or {}).get("value", "")),
            "credit": _strip_html((meta.get("Credit") or {}).get("value", "")),
            "license": license_name,
            "license_url": _strip_html((meta.get("LicenseUrl") or {}).get("value", "")),
        }
    return None


def _download(url: str, destination: Path) -> None:
    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    destination.write_bytes(response.content)


def _make_storyboard_visual(
    destination: Path,
    topic: str,
    scene: dict,
    seed: int,
) -> None:
    rng = random.Random(seed)
    width, height = 1080, 1920
    base = Image.new("RGB", (width, height), (38, 82, 166))
    draw = ImageDraw.Draw(base)

    # Bright game-like layered background instead of a branded text card.
    for i in range(10):
        y = int(height * (i / 10))
        shade = 65 + i * 8
        draw.rectangle((0, y, width, y + height // 10 + 2), fill=(35, min(180, shade + 55), min(235, shade + 95)))

    # Simple blocky Roblox-inspired player silhouette.
    cx = width // 2 + rng.randint(-80, 80)
    ground = 1390
    skin = (235, 188, 135)
    shirt = (rng.randint(55, 110), rng.randint(110, 210), rng.randint(160, 240))
    pants = (35, 48, 76)
    draw.rounded_rectangle((cx - 120, ground - 520, cx + 120, ground - 300), radius=35, fill=skin)
    draw.rectangle((cx - 150, ground - 295, cx + 150, ground + 40), fill=shirt)
    draw.rectangle((cx - 145, ground + 40, cx - 15, ground + 360), fill=pants)
    draw.rectangle((cx + 15, ground + 40, cx + 145, ground + 360), fill=pants)
    draw.rectangle((cx - 250, ground - 260, cx - 150, ground + 20), fill=skin)
    draw.rectangle((cx + 150, ground - 260, cx + 250, ground + 20), fill=skin)

    # Scene-specific prop cues from the requested visual.
    query = str(scene.get("visual_query") or topic).lower()
    if any(k in query for k in ("door", "vault", "room", "secret")):
        draw.rounded_rectangle((90, 500, 430, 1250), radius=20, fill=(40, 46, 66), outline=(255, 221, 74), width=18)
        draw.ellipse((365, 850, 400, 885), fill=(255, 221, 74))
    if any(k in query for k in ("coin", "robux", "money", "rare", "item", "drop")):
        for x, y in ((190, 350), (830, 540), (220, 1450)):
            draw.ellipse((x - 65, y - 65, x + 65, y + 65), fill=(255, 216, 63), outline=(255, 244, 170), width=10)
    if any(k in query for k in ("lag", "disconnect", "wifi", "server")):
        for n in range(3):
            r = 95 + n * 65
            draw.arc((width - 380 - r, 280 - r, width - 380 + r, 280 + r), 205, 335, fill=(255, 255, 255), width=18)
        draw.ellipse((width - 395, 335, width - 365, 365), fill=(255, 255, 255))
    if any(k in query for k in ("win", "victory", "finish", "goal")):
        draw.polygon([(760, 360), (900, 430), (830, 570), (690, 520), (690, 410)], fill=(255, 218, 62))

    # One short beat label only, like a modern caption card—not a generic template title.
    emphasis = (scene.get("on_screen_emphasis") or "").strip().upper()[:36]
    if emphasis:
        font = _font(72, bold=True)
        box = draw.textbbox((0, 0), emphasis, font=font)
        tw = box[2] - box[0]
        pad = 28
        x1 = max(45, (width - tw) // 2 - pad)
        x2 = min(width - 45, (width + tw) // 2 + pad)
        draw.rounded_rectangle((x1, 145, x2, 270), radius=28, fill=(8, 12, 23))
        draw.text(((width - tw) / 2, 172), emphasis, font=font, fill=(255, 255, 255))

    # Soft depth and vignette.
    vignette = Image.new("RGBA", base.size, (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    vdraw.rectangle((0, 0, width, 160), fill=(0, 0, 0, 70))
    vdraw.rectangle((0, 1600, width, height), fill=(0, 0, 0, 85))
    final = Image.alpha_composite(base.convert("RGBA"), vignette).convert("RGB")
    final.save(destination, quality=94)


def _try_ai_scene(
    scene: dict,
    destination: Path,
    index: int,
    topic: str,
    reference_image: str | Path | None = None,
) -> dict[str, Any] | None:
    try:
        state = comfyui_health()
        if not state.get("ok") or not state.get("image_ready"):
            return None
        is_story = bool(scene.get("character_visuals") or scene.get("keyframe_prompt"))
        base_prompt = scene_image_prompt(scene, topic)
        if is_story:
            direction = {
                "prompt": (
                    base_prompt
                    + " Authentic Roblox R15 gameplay render. Square block head, simple Roblox face, rectangular torso, "
                    "segmented block arms and legs, classic Roblox plastic avatar proportions. Crisp current Roblox-engine "
                    "look, polished lighting and depth, but still unmistakably Roblox rather than a generic 3D cartoon. "
                    "Keep all important action below the top safe area."
                ),
                "negative_prompt": (
                    "words, letters, numbers, typography, subtitles, captions, title card, fake game title, signs, "
                    "logo, watermark, UI text, gibberish writing, random symbols, "
                    "human body, realistic human, Pixar, Disney, clay, Playmobil, LEGO, minifigure, Minecraft, voxel person, "
                    "Funko, chibi, doll, generic mobile game character, rounded human head, realistic hands, fingers, "
                    "old low-poly 2010s look, flat lighting, blurry, low detail, extra limbs, duplicate character, "
                    "changed clothes, changed hair, deformed face, cluttered composition"
                ),
            }
        else:
            direction = {
                "prompt": base_prompt + " Bright polished modern Roblox-style 3D scene, clean lighting, no text.",
                "negative_prompt": "text, logo, watermark, blurry, low quality, clutter, broken anatomy",
            }
        character_key = "|".join(
            str(x) for x in scene.get("character_visuals", []) if x
        ) or topic
        seed_key = f"{character_key}|{scene.get('game_name','')}|scene:{index}"
        stable_seed = zlib.crc32(seed_key.encode("utf-8")) & 0x7FFFFFFF

        if is_story and reference_image and Path(reference_image).exists():
            if state.get("story_image_ready"):
                result = generate_story_keyframe(
                    prompt=(
                        direction["prompt"]
                        + " Treat the supplied reference image as the exact avatar/body-shape and continuity reference. "
                        "Keep the Roblox R15 body geometry and outfit identity, but change pose, camera and environment "
                        "to match this scene. Do not copy any text from the reference."
                    ),
                    reference_path=reference_image,
                    seed=stable_seed,
                    job_id=f"storyframe_{index}_{random.randint(1000,9999)}",
                )
            else:
                ref_path = Path(reference_image)
                first_cast_reference = ref_path.name.lower().startswith("cast_reference")
                result = generate_ai_image_from_reference(
                    prompt=direction["prompt"],
                    negative_prompt=direction["negative_prompt"],
                    reference_path=reference_image,
                    aspect="9:16",
                    steps=30 if first_cast_reference else 26,
                    cfg=6.2,
                    denoise=0.72 if first_cast_reference else 0.58,
                    seed=stable_seed,
                    job_id=f"storyframe_{index}_{random.randint(1000,9999)}",
                )
        else:
            result = generate_ai_image(
                prompt=direction["prompt"],
                negative_prompt=direction["negative_prompt"],
                aspect="9:16",
                steps=28 if is_story else 20,
                cfg=6.2 if is_story else 6.5,
                seed=stable_seed if is_story else None,
                job_id=f"shortscene_{index}_{random.randint(1000,9999)}",
            )
        source = Path(result["path"])
        image = Image.open(source).convert("RGB")
        image.save(destination, quality=94)
        return {
            "path": str(destination),
            "kind": "ai_generated_scene",
            "query": scene.get("visual_query") or topic,
            "attribution": None,
            "prompt": direction["prompt"],
            "seed": result.get("seed"),
            "checkpoint": result.get("checkpoint"),
            "image_backend": result.get("backend", "sdxl_t2i"),
            "continuity_reference": str(reference_image) if reference_image else None,
        }
    except Exception:
        return None


def _try_ai_video_scene(
    scene: dict,
    job_dir: Path,
    index: int,
    topic: str,
    duration: float,
) -> dict[str, Any] | None:
    state = comfyui_health()
    if not state.get("video_ready"):
        return None

    role = str(scene.get("role", "")).lower()
    is_story = bool(scene.get("character_visuals") or scene.get("motion_prompt"))
    base_prompt = scene_video_prompt(scene, topic)
    if is_story:
        direction = {
            "prompt": (
                base_prompt
                + " One continuous cinematic shot. Modern Roblox-style 3D movie quality, polished lighting, "
                "clean materials, believable blocky character movement, stable identity, stable outfit, "
                "clear foreground/background separation, no sudden scene change."
            ),
            "negative_prompt": (
                "text, subtitles, logo, watermark, 2010s low-poly look, flat lighting, flicker, morphing, "
                "melting face, changed clothing, changed hair, duplicate character, extra limbs, camera teleport, "
                "random objects appearing, blur, compression artifacts"
            ),
        }
    else:
        direction = {
            "prompt": base_prompt + " Smooth modern game animation, one clear action, stable camera, no text.",
            "negative_prompt": "text, logo, watermark, flicker, morphing, duplicate character, blur",
        }
    try:
        result = generate_ai_video(
            prompt=direction["prompt"],
            negative_prompt=direction["negative_prompt"],
            aspect="9:16",
            seconds=max(3, min(5, round(duration))),
            motion_strength=1.0,
            seed=None,
            job_id=f"shortvideo_{index}_{random.randint(1000,9999)}",
        )
    except Exception as exc:
        return {
            "kind": "ai_video_failed",
            "error": str(exc),
            "query": scene.get("visual_query") or topic,
        }

    return {
        "path": result["path"],
        "kind": "ai_generated_video",
        "query": scene.get("visual_query") or topic,
        "attribution": None,
        "prompt": direction["prompt"],
        "seed": result.get("seed"),
    }


def prepare_visual(
    scene: dict,
    job_dir: Path,
    index: int,
    topic: str,
    *,
    duration: float = 3.0,
    reference_image: str | Path | None = None,
) -> dict:
    visual_dir = job_dir / "visuals"
    visual_dir.mkdir(parents=True, exist_ok=True)
    destination = visual_dir / f"scene_{index:02d}.jpg"
    query = scene.get("visual_query") or topic
    is_roblox = "roblox" in f"{topic} {query}".lower()

    if is_roblox:
        role = str(scene.get("role", "")).lower()
        priority = str(scene.get("motion_priority", "")).lower()
        is_story = bool(scene.get("character_visuals") or scene.get("keyframe_prompt"))
        if is_story:
            wants_video = (
                role in {"hook", "reveal", "payoff"}
                or priority == "high"
                or (priority == "medium" and index % 2 == 0)
            )

            # Story mode is keyframe-first: create the exact character/shot first,
            # then animate that frame when the stronger I2V backend is installed.
            keyframe = _try_ai_scene(
                scene,
                destination,
                index,
                topic,
                reference_image=reference_image,
            )
            if not keyframe:
                raise RuntimeError(
                    "Could not create the cinematic story keyframe. "
                    "Story mode will not fall back to generic block characters."
                )

            state = comfyui_health()
            if wants_video and state.get("story_video_ready"):
                direction = {
                    "prompt": (
                        scene_video_prompt(scene, topic)
                        + " Animate from the supplied keyframe like an actual Roblox gameplay cinematic. "
                        "Preserve square Roblox heads, rectangular torsos and segmented R15 block limbs frame-to-frame. "
                        "Preserve the exact avatar face, hair accessory, clothing textures, colours, body proportions "
                        "and game environment. One controlled camera move and one readable action only. "
                        "Movement should resemble Roblox character animation, not human motion capture."
                    ),
                    "negative_prompt": (
                        "words, letters, numbers, subtitles, captions, title, logo, watermark, UI text, "
                        "human anatomy, realistic human, Pixar, clay, LEGO, Minecraft, generic cartoon person, "
                        "rounded human face, fingers, identity drift, changed clothes, changed hair, face morphing, "
                        "duplicate character, extra limbs, flicker, camera teleport, random object pop-in, old low-poly look"
                    ),
                }
                try:
                    animated = generate_story_video_from_image(
                        prompt=direction["prompt"],
                        negative_prompt=direction["negative_prompt"],
                        image_path=keyframe["path"],
                        seconds=max(2, min(4, round(duration))),
                        job_id=f"storyi2v_{index}_{random.randint(1000,9999)}",
                    )
                    return {
                        "path": animated["path"],
                        "kind": "ai_generated_video",
                        "backend": animated.get("backend", "ltx_i2v"),
                        "query": scene.get("visual_query") or topic,
                        "attribution": None,
                        "prompt": direction["prompt"],
                        "seed": animated.get("seed"),
                        "keyframe_path": keyframe["path"],
                        "keyframe_prompt": keyframe.get("prompt"),
                    }
                except Exception as exc:
                    # Keep the polished keyframe instead of replacing it with a poor clip.
                    keyframe["animation_error"] = str(exc)
                    keyframe["kind"] = "ai_generated_scene"
                    return keyframe

            # Do not fall back to the old text-to-video model in Story mode.
            # Its character/visual quality is below the bar for the mini-movie format.
            # If cinematic I2V is unavailable, keep the polished keyframe and let the
            # pipeline's story quality gate explain what is missing.
            return keyframe

        wants_video = role in {"hook", "reveal", "payoff"} or index % 4 == 0
        if wants_video:
            video = _try_ai_video_scene(scene, job_dir, index, topic, duration)
            if video and video.get("kind") == "ai_generated_video":
                return video

        generated = _try_ai_scene(scene, destination, index, topic)
        if generated:
            return generated

        state = comfyui_health()
        missing = ", ".join(state.get("missing_video_models") or [])
        details = ""
        if wants_video and missing:
            details = f" Missing Wan video models: {missing}."
        raise RuntimeError(
            "Could not create a real Roblox visual for this scene."
            + details
            + " Shorts Studio will not use the old blocky placeholder visuals anymore."
        )

    attribution = search_commons(query)
    if attribution and attribution.get("download_url"):
        raw = visual_dir / f"scene_{index:02d}_raw"
        _download(attribution["download_url"], raw)
        image = Image.open(raw).convert("RGB")
        image.thumbnail((1800, 1800))
        image.save(destination, quality=92)
        raw.unlink(missing_ok=True)
        return {
            "path": str(destination),
            "kind": "wikimedia_commons",
            "query": query,
            "attribution": attribution,
        }

    generated = _try_ai_scene(scene, destination, index, topic)
    if generated:
        return generated

    raise RuntimeError(
        "No usable real visual could be generated for this scene. "
        "Placeholder storyboard rendering is disabled."
    )
