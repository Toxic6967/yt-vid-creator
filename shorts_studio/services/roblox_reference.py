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


def _shade(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(v * factor))) for v in rgb)


def _draw_part(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    radius: int,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=_shade(fill, 0.73), width=max(1, radius // 4))
    inset = max(2, radius // 2)
    if x2 - x1 > inset * 3 and y2 - y1 > inset * 3:
        draw.line(
            (x1 + inset, y1 + inset, x2 - inset, y1 + inset),
            fill=_shade(fill, 1.13),
            width=max(1, radius // 5),
        )


def _draw_r15(
    draw: ImageDraw.ImageDraw,
    cx: int,
    ground: int,
    scale: float,
    palette: dict,
) -> None:
    """Text-free R15-shaped conditioning figure, intentionally unlike voxel/Minecraft anatomy."""
    head_w = int(92 * scale)
    head_h = int(86 * scale)
    torso_top = int(88 * scale)
    torso_bottom = int(102 * scale)
    torso_h = int(126 * scale)
    limb_w = int(30 * scale)
    upper_arm = int(64 * scale)
    lower_arm = int(61 * scale)
    upper_leg = int(72 * scale)
    lower_leg = int(72 * scale)
    joint_gap = max(3, int(8 * scale))

    total_h = head_h + int(11 * scale) + torso_h + upper_leg + lower_leg + joint_gap
    head_y = ground - total_h
    head_x = cx - head_w // 2

    # R15 legs: narrower separated upper/lower segments with visible joints.
    hip_y = head_y + head_h + int(11 * scale) + torso_h
    leg_sep = int(12 * scale)
    for side in (-1, 1):
        lx = cx + side * (leg_sep + limb_w // 2) - limb_w // 2
        _draw_part(
            draw,
            (lx, hip_y, lx + limb_w, hip_y + upper_leg),
            palette["pants"],
            max(4, int(8 * scale)),
        )
        lower_y = hip_y + upper_leg + joint_gap
        _draw_part(
            draw,
            (lx, lower_y, lx + limb_w, lower_y + lower_leg),
            palette["pants"],
            max(4, int(8 * scale)),
        )
        shoe_h = int(18 * scale)
        draw.rounded_rectangle(
            (
                lx - int(4 * scale),
                lower_y + lower_leg - shoe_h,
                lx + limb_w + int(10 * scale),
                lower_y + lower_leg + int(4 * scale),
            ),
            radius=max(3, int(6 * scale)),
            fill=palette["shoes"],
            outline=_shade(palette["shoes"], 0.72),
            width=max(1, int(2 * scale)),
        )

    # R15 torso has a subtle shoulder-to-waist taper instead of a Minecraft rectangle.
    torso_y = head_y + head_h + int(11 * scale)
    torso_poly = [
        (cx - torso_top // 2, torso_y),
        (cx + torso_top // 2, torso_y),
        (cx + torso_bottom // 2, torso_y + torso_h),
        (cx - torso_bottom // 2, torso_y + torso_h),
    ]
    draw.polygon(torso_poly, fill=palette["shirt"], outline=_shade(palette["shirt"], 0.72))
    draw.line(
        (cx - torso_top // 2 + int(8 * scale), torso_y + int(8 * scale),
         cx + torso_top // 2 - int(8 * scale), torso_y + int(8 * scale)),
        fill=_shade(palette["shirt"], 1.12),
        width=max(1, int(3 * scale)),
    )

    # R15 arms: shoulder / forearm / hand are visibly separate pieces.
    shoulder_y = torso_y + int(6 * scale)
    for side in (-1, 1):
        ax = (
            cx - torso_top // 2 - limb_w - int(7 * scale)
            if side < 0
            else cx + torso_top // 2 + int(7 * scale)
        )
        _draw_part(
            draw,
            (ax, shoulder_y, ax + limb_w, shoulder_y + upper_arm),
            palette["shirt"],
            max(4, int(8 * scale)),
        )
        fore_y = shoulder_y + upper_arm + joint_gap
        _draw_part(
            draw,
            (ax, fore_y, ax + limb_w, fore_y + lower_arm),
            palette["skin"],
            max(4, int(8 * scale)),
        )
        hand_r = max(5, int(13 * scale))
        hand_cx = ax + limb_w // 2
        hand_cy = fore_y + lower_arm + hand_r // 2
        draw.rounded_rectangle(
            (
                hand_cx - hand_r,
                hand_cy - hand_r,
                hand_cx + hand_r,
                hand_cy + hand_r,
            ),
            radius=hand_r // 2,
            fill=palette["skin"],
            outline=_shade(palette["skin"], 0.78),
            width=max(1, int(2 * scale)),
        )

    # Beveled classic Roblox head, not a voxel cube.
    _draw_part(
        draw,
        (head_x, head_y, head_x + head_w, head_y + head_h),
        palette["skin"],
        max(8, int(14 * scale)),
    )

    # Classic Roblox-style face decal: tiny oval eyes + simple smile.
    eye_w = max(2, int(5 * scale))
    eye_h = max(4, int(8 * scale))
    eye_y = head_y + int(head_h * 0.48)
    for ex in (head_x + int(head_w * 0.35), head_x + int(head_w * 0.65)):
        draw.ellipse(
            (ex - eye_w, eye_y - eye_h, ex + eye_w, eye_y + eye_h),
            fill=(25, 27, 30),
        )
    mouth_box = (
        head_x + int(head_w * 0.34),
        head_y + int(head_h * 0.56),
        head_x + int(head_w * 0.66),
        head_y + int(head_h * 0.78),
    )
    draw.arc(
        mouth_box,
        15,
        165,
        fill=(35, 36, 38),
        width=max(2, int(4 * scale)),
    )

    # Catalog-hair silhouette rather than a Minecraft hair block.
    hair_y = head_y - int(5 * scale)
    draw.rounded_rectangle(
        (
            head_x + int(3 * scale),
            hair_y,
            head_x + head_w - int(3 * scale),
            head_y + int(17 * scale),
        ),
        radius=max(5, int(10 * scale)),
        fill=palette["hair"],
    )
    spikes = [
        (0.05, 0.20),
        (0.20, -0.12),
        (0.34, 0.10),
        (0.50, -0.16),
        (0.66, 0.08),
        (0.82, -0.08),
        (0.95, 0.17),
    ]
    pts = []
    for x_ratio, y_ratio in spikes:
        pts.append(
            (
                head_x + int(head_w * x_ratio),
                head_y + int(head_h * y_ratio),
            )
        )
    pts += [
        (head_x + head_w - int(4 * scale), head_y + int(22 * scale)),
        (head_x + int(4 * scale), head_y + int(22 * scale)),
    ]
    draw.polygon(pts, fill=palette["hair"])


def build_cast_reference(
    characters: list[dict[str, Any]],
    destination: Path,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = 576, 1024

    # Neutral text-free studio reference. It deliberately contains no world/background
    # details for FLUX to accidentally copy into every scene.
    image = Image.new("RGB", (width, height), (211, 216, 223))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, int(height * 0.78), width, height), fill=(182, 187, 194))
    draw.ellipse(
        (int(width * 0.08), int(height * 0.82), int(width * 0.92), int(height * 0.95)),
        fill=(162, 167, 174),
    )

    count = max(1, min(3, len(characters)))
    xs = {
        1: [width // 2],
        2: [int(width * 0.34), int(width * 0.66)],
        3: [int(width * 0.23), int(width * 0.50), int(width * 0.77)],
    }[count]
    scale = 1.08 if count == 1 else (0.86 if count == 2 else 0.69)
    ground = int(height * 0.86)

    for idx, character in enumerate(characters[:count]):
        cid = str(character.get("id") or "").lower()
        palette = PALETTES.get(cid, PALETTES["max"])
        _draw_r15(draw, xs[idx], ground, scale, palette)

    image.save(destination, quality=96)
    return destination


def build_scene_cast_reference(
    scene: dict[str, Any],
    characters: list[dict[str, Any]],
    destination: Path,
) -> Path:
    visible = {str(x).lower() for x in (scene.get("characters") or []) if x}
    selected = [
        character
        for character in characters
        if str(character.get("id") or "").lower() in visible
    ]
    if not selected:
        selected = characters[:1]
    return build_cast_reference(selected, destination)



def compose_character_reference_sheet(
    character_paths: list[str | Path],
    destination: Path,
) -> Path:
    """Combine polished one-character refs into a neutral scene-specific cast sheet."""
    paths = [Path(p) for p in character_paths if p and Path(p).exists()]
    if not paths:
        raise RuntimeError("No polished Roblox character references were available.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = 576, 1024
    canvas = Image.new("RGB", (width, height), (216, 220, 226))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, int(height * 0.82), width, height), fill=(187, 191, 198))

    count = min(3, len(paths))
    gap = 14
    panel_w = (width - gap * (count + 1)) // count
    panel_h = int(height * 0.84)

    for idx, path in enumerate(paths[:count]):
        image = Image.open(path).convert("RGB")
        # Crop toward the character, keeping full-body portrait proportions.
        src_ratio = image.width / image.height
        target_ratio = panel_w / panel_h
        if src_ratio > target_ratio:
            crop_w = int(image.height * target_ratio)
            left = max(0, (image.width - crop_w) // 2)
            image = image.crop((left, 0, left + crop_w, image.height))
        else:
            crop_h = int(image.width / target_ratio)
            top = max(0, (image.height - crop_h) // 2)
            image = image.crop((0, top, image.width, top + crop_h))

        image = image.resize((panel_w, panel_h), Image.Resampling.LANCZOS)
        x = gap + idx * (panel_w + gap)
        y = int(height * 0.05)
        canvas.paste(image, (x, y))

    canvas.save(destination, quality=96)
    return destination



def build_environment_seed(destination: Path) -> Path:
    """Neutral text-free Roblox-like baseplate used only to start environment generation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = 576, 1024
    image = Image.new("RGB", (width, height), (115, 176, 226))
    draw = ImageDraw.Draw(image)

    # Simple horizon + baseplate gives FLUX a game-space composition without
    # biasing it toward any specific room from a previous shot.
    horizon = int(height * 0.55)
    draw.rectangle((0, 0, width, horizon), fill=(115, 176, 226))
    draw.rectangle((0, horizon, width, height), fill=(132, 145, 151))

    # Subtle perspective guide lines; no text, no characters, no props.
    vanishing_x = width // 2
    vanishing_y = horizon + int(height * 0.02)
    for x in range(-width, width * 2, 96):
        draw.line((x, height, vanishing_x, vanishing_y), fill=(121, 132, 138), width=2)
    for y in range(horizon + 90, height, 110):
        draw.line((0, y, width, y), fill=(121, 132, 138), width=2)

    image.save(destination, quality=95)
    return destination
