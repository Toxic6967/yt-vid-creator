from __future__ import annotations

import html
import random
import re
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import settings
from .comfyui_client import generate_ai_image, generate_ai_video, health as comfyui_health
from .media_director import enhance_image_prompt, enhance_video_prompt, scene_image_prompt

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


def _try_ai_scene(scene: dict, destination: Path, index: int, topic: str) -> dict[str, Any] | None:
    try:
        state = comfyui_health()
        if not state.get("ok") or not state.get("image_ready"):
            return None
        direction = enhance_image_prompt(
            scene_image_prompt(scene, topic),
            style="roblox_bright",
            purpose="hook" if scene.get("role") == "hook" else "scene_visual",
        )
        result = generate_ai_image(
            prompt=direction["prompt"],
            negative_prompt=direction["negative_prompt"],
            aspect="9:16",
            steps=18,
            cfg=6.5,
            seed=None,
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
    direction = enhance_video_prompt(
        scene_image_prompt(scene, topic),
        style="roblox_bright",
        camera="push_in" if role == "hook" else "auto",
        purpose="hook" if role == "hook" else ("reveal" if role in {"reveal", "payoff"} else "b_roll"),
        seconds=max(3, min(5, round(duration))),
    )
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
) -> dict:
    visual_dir = job_dir / "visuals"
    visual_dir.mkdir(parents=True, exist_ok=True)
    destination = visual_dir / f"scene_{index:02d}.jpg"
    query = scene.get("visual_query") or topic
    is_roblox = "roblox" in f"{topic} {query}".lower()

    if is_roblox:
        role = str(scene.get("role", "")).lower()
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
