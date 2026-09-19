from __future__ import annotations

import html
import random
import re
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import settings

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSE_MARKERS = ("cc by", "cc-by", "cc by-sa", "cc-by-sa", "cc0", "public domain", "pd-")


def _strip_html(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


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
        license_key = license_name.lower()
        if not any(marker in license_key for marker in ALLOWED_LICENSE_MARKERS):
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


def _make_procedural_card(destination: Path, topic: str, emphasis: str, seed: int) -> None:
    rng = random.Random(seed)
    width, height = 1080, 1920
    base = Image.new("RGB", (width, height), (13, 18, 28))
    draw = ImageDraw.Draw(base)
    for _ in range(14):
        x = rng.randint(-250, width)
        y = rng.randint(-250, height)
        radius = rng.randint(120, 420)
        shade = rng.randint(25, 80)
        draw.ellipse((x, y, x + radius, y + radius), fill=(shade, shade + rng.randint(0, 25), shade + rng.randint(10, 55)))
    base = base.filter(ImageFilter.GaussianBlur(42))
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle((80, 620, 1000, 1280), radius=42, fill=(7, 10, 16, 190))
    title_font = _font(82, bold=True)
    small_font = _font(38, bold=False)
    label = (emphasis or topic).strip().upper()[:55]
    words = label.split()
    lines = []
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        if odraw.textlength(test, font=title_font) > 800 and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    y = 760
    for text in lines[:4]:
        bbox = odraw.textbbox((0, 0), text, font=title_font)
        tw = bbox[2] - bbox[0]
        odraw.text(((width - tw) / 2, y), text, font=title_font, fill=(255, 255, 255, 255))
        y += 104
    odraw.text((90, 1170), "SHORTS STUDIO • GENERATED VISUAL", font=small_font, fill=(210, 215, 225, 220))
    final = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    final.save(destination, quality=94)


def prepare_visual(scene: dict, job_dir: Path, index: int, topic: str) -> dict:
    visual_dir = job_dir / "visuals"
    visual_dir.mkdir(parents=True, exist_ok=True)
    destination = visual_dir / f"scene_{index:02d}.jpg"
    query = scene.get("visual_query") or topic
    attribution = search_commons(query)
    if attribution and attribution.get("download_url"):
        try:
            raw = visual_dir / f"scene_{index:02d}_raw"
            _download(attribution["download_url"], raw)
            image = Image.open(raw).convert("RGB")
            image.thumbnail((1800, 1800))
            image.save(destination, quality=92)
            raw.unlink(missing_ok=True)
            return {"path": str(destination), "kind": "wikimedia_commons", "query": query, "attribution": attribution}
        except Exception:
            pass

    _make_procedural_card(destination, topic, scene.get("on_screen_emphasis", ""), index * 991)
    return {"path": str(destination), "kind": "generated_procedural", "query": query, "attribution": None}
