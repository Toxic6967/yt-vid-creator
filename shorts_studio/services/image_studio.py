from __future__ import annotations

import random
import textwrap
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import OUTPUT_DIR
from ..db import save_generated_image


def _font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _size(aspect: str) -> tuple[int, int]:
    return {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}[aspect]


def create_graphic(prompt: str, headline: str, aspect: str = "9:16") -> dict:
    image_id = uuid.uuid4().hex[:12]
    width, height = _size(aspect)
    folder = OUTPUT_DIR / "images"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"{image_id}.jpg"

    rng = random.Random(f"{prompt}|{headline}|{aspect}")
    image = Image.new("RGB", (width, height), (8, 12, 22))
    draw = ImageDraw.Draw(image)
    for _ in range(18):
        x = rng.randint(-width // 4, width)
        y = rng.randint(-height // 4, height)
        r = rng.randint(max(80, width // 12), max(180, width // 3))
        c = (rng.randint(25, 100), rng.randint(35, 110), rng.randint(70, 165))
        draw.ellipse((x, y, x + r, y + r), fill=c)
    image = image.filter(ImageFilter.GaussianBlur(max(30, width // 30)))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    pad = int(width * .07)
    top = int(height * .20)
    bottom = int(height * .82)
    od.rounded_rectangle((pad, top, width-pad, bottom), radius=max(24, width//28), fill=(5, 8, 15, 205))

    title = (headline.strip() or prompt.strip()).upper()[:70]
    title_font = _font(max(42, width // 13), True)
    sub_font = _font(max(24, width // 31), False)
    max_chars = 16 if aspect == "9:16" else 25
    lines = textwrap.wrap(title, width=max_chars)[:5]
    y = top + int(height * .08)
    for line in lines:
        bbox = od.textbbox((0, 0), line, font=title_font)
        tw = bbox[2] - bbox[0]
        od.text(((width - tw) / 2, y), line, font=title_font, fill=(255,255,255,255))
        y += int(title_font.size * 1.15)

    sub = prompt.strip()[:150]
    for line in textwrap.wrap(sub, width=46)[:3]:
        bbox = od.textbbox((0, 0), line, font=sub_font)
        tw = bbox[2] - bbox[0]
        od.text(((width - tw) / 2, bottom - int(height*.12)), line, font=sub_font, fill=(192,207,230,235))
        bottom += int(sub_font.size * 1.2)

    badge_font = _font(max(20, width // 42), True)
    od.text((pad + 10, int(height*.91)), "SHORTS STUDIO • LOCAL GRAPHIC", font=badge_font, fill=(100,220,255,230))
    final = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    final.save(output, quality=94)
    save_generated_image(image_id, prompt, headline, aspect, str(output))
    return {"id": image_id, "path": str(output), "aspect": aspect, "prompt": prompt, "headline": headline}
