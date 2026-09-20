from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


PALETTES = {
    "max": {
        "skin": (232, 189, 143),
        "shirt": (45, 94, 205),
        "pants": (31, 35, 45),
        "shoes": (236, 239, 244),
        "hair": (67, 42, 28),
    },
    "mia": {
        "skin": (224, 177, 132),
        "shirt": (126, 69, 190),
        "pants": (34, 35, 43),
        "shoes": (239, 239, 242),
        "hair": (38, 27, 30),
    },
    "kai": {
        "skin": (218, 171, 127),
        "shirt": (166, 40, 44),
        "pants": (33, 34, 40),
        "shoes": (176, 43, 48),
        "hair": (25, 24, 27),
    },
}


def _draw_r15(draw: ImageDraw.ImageDraw, cx: int, ground: int, scale: float, palette: dict) -> None:
    # Deliberately rigid R15-like conditioning geometry: square head,
    # rectangular torso and segmented block limbs.
    head = int(112 * scale)
    torso_w = int(108 * scale)
    torso_h = int(150 * scale)
    limb_w = int(42 * scale)
    upper = int(82 * scale)
    lower = int(78 * scale)

    head_y = ground - (head + torso_h + upper + lower)
    head_x = cx - head // 2

    # legs: upper + lower segments
    hip_y = head_y + head + torso_h
    leg_gap = int(15 * scale)
    for side in (-1, 1):
        lx = cx + side * (leg_gap + limb_w // 2) - limb_w // 2
        draw.rounded_rectangle(
            (lx, hip_y, lx + limb_w, hip_y + upper),
            radius=max(2, int(5 * scale)),
            fill=palette["pants"],
        )
        draw.rounded_rectangle(
            (lx, hip_y + upper + 2, lx + limb_w, hip_y + upper + lower),
            radius=max(2, int(5 * scale)),
            fill=palette["pants"],
        )
        shoe_h = int(22 * scale)
        draw.rectangle(
            (lx - int(3 * scale), hip_y + upper + lower - shoe_h,
             lx + limb_w + int(8 * scale), hip_y + upper + lower),
            fill=palette["shoes"],
        )

    # torso
    torso_x = cx - torso_w // 2
    torso_y = head_y + head
    draw.rounded_rectangle(
        (torso_x, torso_y, torso_x + torso_w, torso_y + torso_h),
        radius=max(3, int(6 * scale)),
        fill=palette["shirt"],
    )

    # arms: upper + lower segments
    arm_y = torso_y + int(8 * scale)
    for side in (-1, 1):
        ax = torso_x - limb_w - int(8 * scale) if side < 0 else torso_x + torso_w + int(8 * scale)
        draw.rounded_rectangle(
            (ax, arm_y, ax + limb_w, arm_y + upper),
            radius=max(2, int(5 * scale)),
            fill=palette["shirt"],
        )
        draw.rounded_rectangle(
            (ax, arm_y + upper + 2, ax + limb_w, arm_y + upper + lower),
            radius=max(2, int(5 * scale)),
            fill=palette["skin"],
        )

    # square head + classic simple face
    draw.rounded_rectangle(
        (head_x, head_y, head_x + head, head_y + head),
        radius=max(3, int(7 * scale)),
        fill=palette["skin"],
    )
    eye = max(3, int(6 * scale))
    eye_y = head_y + int(head * 0.47)
    for ex in (head_x + int(head * 0.32), head_x + int(head * 0.68)):
        draw.rectangle((ex - eye, eye_y - eye, ex + eye, eye_y + eye), fill=(28, 29, 32))
    mouth_y = head_y + int(head * 0.70)
    draw.arc(
        (head_x + int(head * 0.33), mouth_y - int(10 * scale),
         head_x + int(head * 0.67), mouth_y + int(16 * scale)),
        5, 175, fill=(37, 38, 40), width=max(2, int(4 * scale))
    )

    # simple Roblox hair cap/accessory shape
    hair_y = head_y - int(8 * scale)
    draw.rectangle(
        (head_x + int(4 * scale), hair_y, head_x + head - int(4 * scale), head_y + int(24 * scale)),
        fill=palette["hair"],
    )
    draw.polygon(
        [
            (head_x + int(5 * scale), head_y + int(10 * scale)),
            (head_x + int(24 * scale), head_y - int(20 * scale)),
            (head_x + int(44 * scale), head_y + int(5 * scale)),
            (head_x + int(70 * scale), head_y - int(15 * scale)),
            (head_x + head - int(5 * scale), head_y + int(12 * scale)),
        ],
        fill=palette["hair"],
    )


def build_cast_reference(
    characters: list[dict[str, Any]],
    destination: Path,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = 576, 1024

    image = Image.new("RGB", (width, height), (89, 146, 211))
    draw = ImageDraw.Draw(image)

    # Text-free, simple game-like staging. This image is conditioning only.
    draw.rectangle((0, int(height * 0.58), width, height), fill=(87, 164, 88))
    draw.rectangle((0, int(height * 0.76), width, height), fill=(106, 109, 119))
    draw.rectangle((0, int(height * 0.10), width, int(height * 0.58)), fill=(101, 160, 220))

    count = max(1, min(3, len(characters)))
    xs = {
        1: [width // 2],
        2: [int(width * 0.34), int(width * 0.66)],
        3: [int(width * 0.24), int(width * 0.50), int(width * 0.76)],
    }[count]
    scale = 0.86 if count == 1 else (0.70 if count == 2 else 0.58)
    ground = int(height * 0.88)

    for idx, character in enumerate(characters[:count]):
        cid = str(character.get("id") or "").lower()
        palette = PALETTES.get(cid, PALETTES["max"])
        _draw_r15(draw, xs[idx], ground, scale, palette)

    image.save(destination, quality=95)
    return destination
