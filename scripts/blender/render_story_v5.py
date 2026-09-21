from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import zlib
from pathlib import Path

import bpy
from mathutils import Vector


FPS = 30
RENDER_WIDTH = 1080
RENDER_HEIGHT = 1920
AVATAR_HEIGHT = 5.35


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", required=True)
    # Kept for command-line compatibility with the old V4 renderer. V5 builds
    # a deterministic segmented Roblox-style avatar itself so a malformed FBX
    # import can never destroy every generated Short.
    parser.add_argument("--r15-template", required=False, default="")
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        # Remove only orphaned data. Loaded environment images may be reused by
        # Blender during the current shot.
        for block in list(datablocks):
            if getattr(block, "users", 0) == 0:
                try:
                    datablocks.remove(block)
                except Exception:
                    pass


def rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


PALETTES = {
    "player": {
        "skin": rgb("#E2B584"),
        "shirt": rgb("#2864D7"),
        "pants": rgb("#202630"),
        "shoe": rgb("#F4F5F7"),
        "hair": rgb("#4B3023"),
        "accent": rgb("#55B8FF"),
    },
    "friend": {
        "skin": rgb("#DDAA7E"),
        "shirt": rgb("#8149C7"),
        "pants": rgb("#252733"),
        "shoe": rgb("#F1F1F4"),
        "hair": rgb("#2C2028"),
        "accent": rgb("#E4D8FF"),
    },
    "teammate": {
        "skin": rgb("#D5A377"),
        "shirt": rgb("#B33740"),
        "pants": rgb("#20232B"),
        "shoe": rgb("#E8E8EC"),
        "hair": rgb("#1D1D22"),
        "accent": rgb("#FF676F"),
    },
}

FALLBACK_PALETTES = (
    ("#E0B084", "#1D86D8", "#253040", "#F4F5F6", "#31251F", "#58D5FF"),
    ("#C99066", "#E65A4E", "#262A36", "#F3EFE8", "#231B18", "#FFAE5A"),
    ("#B77F5A", "#32A56F", "#202C28", "#ECEFF1", "#151A18", "#7BFFC1"),
    ("#E5B88A", "#E2A82C", "#2E2933", "#F5F3EF", "#34271E", "#FFE56B"),
    ("#C99C78", "#C94BA0", "#272635", "#F3F0F4", "#251C25", "#FF83DA"),
)


def palette_for(cid: str) -> dict[str, tuple[float, float, float]]:
    key = str(cid or "player").lower()
    if key in PALETTES:
        return PALETTES[key]
    raw = FALLBACK_PALETTES[zlib.crc32(key.encode("utf-8")) % len(FALLBACK_PALETTES)]
    names = ("skin", "shirt", "pants", "shoe", "hair", "accent")
    return {name: rgb(value) for name, value in zip(names, raw)}


def new_material(name, color, *, roughness=0.48, emission=0.0, alpha=1.0, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = (*color[:3], 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if emission > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*color[:3], 1.0)
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = (*color[:3], 1.0)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission
    material.diffuse_color = (*color[:3], alpha)
    if alpha < 1.0:
        try:
            material.surface_render_method = "DITHERED"
        except Exception:
            try:
                material.blend_method = "BLEND"
            except Exception:
                pass
    return material


def add_empty(name, parent=None, location=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    obj.location = location
    return obj


def add_child_box(name, parent, location, size, material, bevel=0.075):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new(name="RobloxSoftEdge", type="BEVEL")
        mod.width = bevel
        mod.segments = 2
    obj.parent = parent
    obj.location = location
    return obj


def add_child_sphere(name, parent, location, scale, material, segments=20, rings=10):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=(0, 0, 0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    obj.parent = parent
    obj.location = location
    return obj


def add_child_torus(name, parent, location, major, minor, material, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=36,
        minor_segments=10,
        location=(0, 0, 0),
    )
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    obj.parent = parent
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def key_location(obj, frame, value):
    obj.location = value
    obj.keyframe_insert(data_path="location", frame=frame)


def key_rotation(obj, frame, value):
    if obj is None:
        return
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = value
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def key_scale(obj, frame, value):
    obj.scale = value
    obj.keyframe_insert(data_path="scale", frame=frame)


def _action_fcurves_for_datablock(action, datablock):
    """Return existing F-curves without relying on Blender's removed Action.fcurves API."""
    if action is None:
        return []

    # Blender <= 4.x legacy API.
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        try:
            return list(legacy)
        except Exception:
            pass

    # Blender 4.4+/5.x slotted Actions. Prefer the exact slot attached to this
    # datablock, then gracefully scan any existing channelbags.
    curves = []
    anim_data = getattr(datablock, "animation_data", None)
    action_slot = getattr(anim_data, "action_slot", None) if anim_data else None
    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            if action_slot is not None and hasattr(strip, "channelbag"):
                try:
                    bag = strip.channelbag(action_slot)
                    if bag is not None:
                        curves.extend(list(getattr(bag, "fcurves", []) or []))
                        continue
                except Exception:
                    pass
            for bag in getattr(strip, "channelbags", []) or []:
                try:
                    if action_slot is None or getattr(bag, "slot", None) == action_slot:
                        curves.extend(list(getattr(bag, "fcurves", []) or []))
                except Exception:
                    continue
    return curves


def set_linear_interpolation(obj):
    data = getattr(obj, "animation_data", None)
    action = getattr(data, "action", None) if data else None
    if not action:
        return

    # BEZIER gives the procedural body acting natural ease-in/ease-out. Blender
    # 5.x stores these curves in channelbags rather than action.fcurves.
    for curve in _action_fcurves_for_datablock(action, obj):
        try:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
            curve.update()
        except Exception:
            pass


def build_avatar(cid: str, lane: float, depth: float = 0.0):
    palette = palette_for(cid)
    mats = {
        "skin": new_material(f"{cid}_Skin", palette["skin"], roughness=0.5),
        "shirt": new_material(f"{cid}_Shirt", palette["shirt"], roughness=0.46),
        "pants": new_material(f"{cid}_Pants", palette["pants"], roughness=0.52),
        "shoe": new_material(f"{cid}_Shoes", palette["shoe"], roughness=0.40),
        "hair": new_material(f"{cid}_Hair", palette["hair"], roughness=0.60),
        "accent": new_material(f"{cid}_Accent", palette["accent"], roughness=0.38),
        "face": new_material(f"{cid}_Face", (0.02, 0.02, 0.025), roughness=0.62),
    }

    root = add_empty(f"{cid}_ROOT", None, (lane, depth, 0.0))
    body = add_empty(f"{cid}_BODY", root, (0, 0, 0))

    # The body is intentionally segmented like an R15 avatar instead of one
    # Minecraft-style rectangle.
    add_child_box(f"{cid}_UpperTorso", body, (0, 0, 3.45), (1.42, 0.72, 1.00), mats["shirt"], 0.11)
    add_child_box(f"{cid}_LowerTorso", body, (0, 0.01, 2.68), (1.08, 0.66, 0.58), mats["shirt"], 0.09)

    head = add_empty(f"{cid}_HEAD_PIVOT", body, (0, 0, 4.55))
    add_child_box(f"{cid}_Head", head, (0, 0, 0), (1.18, 0.88, 1.02), mats["skin"], 0.16)

    # Flat classic Roblox-readable face on the side facing the camera (-Y).
    for x in (-0.22, 0.22):
        add_child_box(f"{cid}_Eye", head, (x, -0.455, 0.08), (0.095, 0.032, 0.16), mats["face"], 0.025)
    add_child_box(f"{cid}_MouthL", head, (-0.12, -0.466, -0.17), (0.20, 0.028, 0.045), mats["face"], 0.015).rotation_euler[1] = -0.16
    add_child_box(f"{cid}_MouthR", head, (0.12, -0.466, -0.17), (0.20, 0.028, 0.045), mats["face"], 0.015).rotation_euler[1] = 0.16

    # Catalog-hair silhouette made of soft pieces, not giant floating spheres.
    hair_specs = (
        (-0.34, -0.02, 0.51, 0.42, 0.78, 0.22),
        (0.00, -0.01, 0.58, 0.54, 0.82, 0.24),
        (0.34, -0.02, 0.50, 0.40, 0.76, 0.21),
    )
    for i, (x, y, z, sx, sy, sz) in enumerate(hair_specs):
        add_child_box(f"{cid}_Hair{i}", head, (x, y, z), (sx, sy, sz), mats["hair"], 0.12)

    pivots = {"body": body, "head": head}
    parts = []

    # Arms.
    for side, sign in (("L", -1), ("R", 1)):
        shoulder = add_empty(f"{cid}_{side}_Shoulder", body, (0.91 * sign, 0, 3.72))
        upper = add_child_box(
            f"{cid}_{side}_UpperArm", shoulder, (0, 0, -0.43),
            (0.42, 0.54, 0.86), mats["shirt"], 0.10,
        )
        elbow = add_empty(f"{cid}_{side}_Elbow", shoulder, (0, 0, -0.88))
        lower = add_child_box(
            f"{cid}_{side}_LowerArm", elbow, (0, 0, -0.39),
            (0.38, 0.50, 0.76), mats["skin"], 0.10,
        )
        hand = add_child_box(
            f"{cid}_{side}_Hand", elbow, (0, -0.01, -0.86),
            (0.40, 0.48, 0.28), mats["skin"], 0.11,
        )
        pivots[f"{side.lower()}_shoulder"] = shoulder
        pivots[f"{side.lower()}_elbow"] = elbow
        parts.extend([upper, lower, hand])

    # Legs with separate thigh/shin/foot pieces and visible joint breaks.
    for side, sign in (("L", -1), ("R", 1)):
        hip = add_empty(f"{cid}_{side}_Hip", body, (0.34 * sign, 0, 2.38))
        upper = add_child_box(
            f"{cid}_{side}_UpperLeg", hip, (0, 0, -0.48),
            (0.48, 0.60, 0.94), mats["pants"], 0.10,
        )
        knee = add_empty(f"{cid}_{side}_Knee", hip, (0, 0, -0.99))
        lower = add_child_box(
            f"{cid}_{side}_LowerLeg", knee, (0, 0, -0.43),
            (0.44, 0.56, 0.84), mats["pants"], 0.10,
        )
        foot = add_child_box(
            f"{cid}_{side}_Foot", knee, (0, -0.09, -0.91),
            (0.48, 0.82, 0.27), mats["shoe"], 0.10,
        )
        pivots[f"{side.lower()}_hip"] = hip
        pivots[f"{side.lower()}_knee"] = knee
        parts.extend([upper, lower, foot])

    # Small outfit accent makes otherwise similar recurring characters easier
    # to read on a phone.
    add_child_box(f"{cid}_ChestAccent", body, (0, -0.385, 3.52), (0.70, 0.035, 0.14), mats["accent"], 0.025)

    shadow_mat = new_material(f"{cid}_Shadow", (0.015, 0.017, 0.02), roughness=1.0, alpha=0.20)
    shadow = add_child_sphere(f"{cid}_Shadow", root, (0, 0.12, 0.055), (0.72, 0.34, 0.045), shadow_mat, 24, 10)
    parts.append(shadow)

    return {
        "root": root,
        "body": body,
        "head": head,
        "pivots": pivots,
        "parts": parts,
        "bounds": (-0.75, 0.75, -0.5, 0.5, 0.0, AVATAR_HEIGHT),
        "palette": palette,
    }


def reset_pose(rig, frame, facing="right"):
    p = rig["pivots"]
    yaw = -0.07 if facing == "left" else 0.07
    key_rotation(p["body"], frame, (0, 0, yaw))
    key_rotation(p["head"], frame, (0, 0, 0))
    for key in ("l_shoulder", "r_shoulder", "l_elbow", "r_elbow", "l_hip", "r_hip", "l_knee", "r_knee"):
        key_rotation(p[key], frame, (0, 0, 0))


def animate_actor(actor, rig, frame_end, depth=0.0):
    root = rig["root"]
    p = rig["pivots"]
    clip = str(actor.get("clip") or "idle").lower()
    start_x = float(actor.get("start_lane") or 0.0)
    end_x = float(actor.get("end_lane") if actor.get("end_lane") is not None else start_x)
    facing = str(actor.get("facing") or "right").lower()
    reset_pose(rig, 1, facing)
    reset_pose(rig, frame_end, facing)

    key_location(root, 1, (start_x, depth, 0.0))
    key_location(root, frame_end, (end_x, depth, 0.0))

    mid = max(2, frame_end // 2)
    q1 = max(2, frame_end // 4)
    q3 = max(q1 + 1, frame_end * 3 // 4)

    if clip in {"walk", "run", "dash"}:
        stride = {"walk": 0.42, "run": 0.66, "dash": 0.82}[clip]
        step = {"walk": 10, "run": 7, "dash": 5}[clip]
        bob = {"walk": 0.055, "run": 0.105, "dash": 0.13}[clip]
        frames = list(range(1, frame_end + 1, step))
        if frames[-1] != frame_end:
            frames.append(frame_end)
        for idx, frame in enumerate(frames):
            t = (frame - 1) / max(1, frame_end - 1)
            sign = 1 if idx % 2 == 0 else -1
            z = bob if idx % 2 else 0.0
            key_location(root, frame, (start_x + (end_x - start_x) * t, depth, z))
            key_rotation(p["l_shoulder"], frame, (stride * sign, 0, 0))
            key_rotation(p["r_shoulder"], frame, (-stride * sign, 0, 0))
            key_rotation(p["l_hip"], frame, (-stride * 0.62 * sign, 0, 0))
            key_rotation(p["r_hip"], frame, (stride * 0.62 * sign, 0, 0))
            key_rotation(p["l_knee"], frame, (max(0.0, stride * 0.46 * sign), 0, 0))
            key_rotation(p["r_knee"], frame, (max(0.0, -stride * 0.46 * sign), 0, 0))
        # Secondary head/body motion keeps locomotion from looking like a
        # rigid mannequin sliding across the floor.
        head_sway = -0.07 if facing == "left" else 0.07
        key_rotation(p["head"], q1, (0.025, 0, head_sway))
        key_rotation(p["head"], q3, (-0.018, 0, -head_sway * 0.65))
        if clip == "dash":
            key_rotation(p["body"], q1, (0.08, 0, -0.12 if facing == "left" else 0.12))
            key_rotation(p["body"], q3, (0.04, 0, 0))
    elif clip == "jump":
        key_location(root, q1, (start_x, depth, 0.10))
        key_location(root, mid, ((start_x + end_x) / 2, depth, 1.02))
        key_location(root, q3, (end_x, depth, 0.24))
        key_rotation(p["l_shoulder"], mid, (2.00, -0.25, 0))
        key_rotation(p["r_shoulder"], mid, (2.00, 0.25, 0))
        key_rotation(p["l_hip"], mid, (-0.34, 0, 0))
        key_rotation(p["r_hip"], mid, (0.34, 0, 0))
        key_rotation(p["l_knee"], mid, (0.48, 0, 0))
        key_rotation(p["r_knee"], mid, (0.48, 0, 0))
        # Landing anticipation and recovery instead of one floaty arc.
        key_rotation(p["body"], q1, (-0.08, 0, 0))
        key_rotation(p["body"], q3, (0.14, 0, 0))
        key_rotation(p["l_shoulder"], q3, (0.42, -0.08, 0))
        key_rotation(p["r_shoulder"], q3, (0.42, 0.08, 0))
    elif clip in {"crouch", "hide"}:
        drop = -0.56 if clip == "hide" else -0.38
        key_location(root, mid, ((start_x + end_x) / 2, depth, drop))
        key_rotation(p["body"], mid, (0.22, 0, 0))
        key_rotation(p["l_hip"], mid, (0.38, 0, 0))
        key_rotation(p["r_hip"], mid, (0.38, 0, 0))
        key_rotation(p["l_knee"], mid, (-0.72, 0, 0))
        key_rotation(p["r_knee"], mid, (-0.72, 0, 0))
        if clip == "hide":
            key_location(root, frame_end, (end_x, depth, -0.32))
    elif clip in {"react", "look_back", "turn"}:
        direction = -1.0 if facing == "left" else 1.0
        yaw = {"react": 0.16, "look_back": 0.46, "turn": 0.62}[clip] * direction
        key_rotation(p["body"], q1, (-0.05, 0, yaw))
        key_rotation(p["body"], mid, (-0.10 if clip == "react" else 0, 0, yaw))
        key_rotation(p["head"], mid, (0, 0, yaw * 0.65))
        if clip == "react":
            key_rotation(p["l_shoulder"], mid, (0.72, -0.25, 0))
            key_rotation(p["r_shoulder"], mid, (0.72, 0.25, 0))
        key_rotation(p["head"], q3, (0, 0, yaw * 0.18))
        key_rotation(p["body"], q3, (0, 0, yaw * 0.24))
    elif clip == "point":
        key_rotation(p["r_shoulder"], q1, (1.48, -0.18, -0.05))
        key_rotation(p["r_elbow"], q1, (-0.22, 0, 0))
        key_rotation(p["r_shoulder"], mid, (1.62, -0.22, -0.06))
        key_rotation(p["head"], mid, (0, 0, -0.10))
        key_rotation(p["r_shoulder"], q3, (0.70, -0.10, -0.03))
        key_rotation(p["r_elbow"], q3, (-0.10, 0, 0))
        key_rotation(p["head"], q3, (0, 0, -0.04))
    elif clip in {"open", "push", "pickup"}:
        key_rotation(p["r_shoulder"], q1, (1.12, -0.08, 0))
        key_rotation(p["r_elbow"], q1, (-0.38, 0, 0))
        key_rotation(p["r_shoulder"], mid, (1.38, -0.12, 0))
        key_rotation(p["r_elbow"], mid, (-0.52, 0, 0))
        key_rotation(p["r_shoulder"], q3, (0.46, -0.04, 0))
        key_rotation(p["r_elbow"], q3, (-0.12, 0, 0))
        key_rotation(p["head"], q1, (0.06, 0, -0.08 if facing == "left" else 0.08))
        key_rotation(p["head"], q3, (0, 0, 0))
        if clip == "pickup":
            key_location(root, mid, ((start_x + end_x) / 2, depth, -0.28))
            key_rotation(p["body"], mid, (0.30, 0, 0))
            key_rotation(p["l_hip"], mid, (0.20, 0, 0))
            key_rotation(p["r_hip"], mid, (0.20, 0, 0))
    elif clip in {"attack", "power_cast", "ground_slam", "shield"}:
        key_rotation(p["r_shoulder"], q1, (1.55, -0.32, 0))
        key_rotation(p["l_shoulder"], q1, (0.95, 0.28, 0))
        key_rotation(p["body"], q1, (0.05, 0, 0.10))
        key_rotation(p["r_shoulder"], mid, (1.15, 0.15, 0))
        key_rotation(p["l_shoulder"], mid, (1.15, -0.15, 0))
        if clip == "ground_slam":
            key_location(root, q1, (start_x, depth, 0.52))
            key_location(root, mid, ((start_x + end_x) / 2, depth, -0.08))
            key_rotation(p["body"], mid, (0.34, 0, 0))
    elif clip in {"fall", "stumble"}:
        key_rotation(p["body"], q1, (0.12, 0.10, 0.18))
        key_rotation(p["body"], mid, (0.22, 0.26, 0.28))
        if clip == "fall":
            key_location(root, frame_end, (end_x, depth, -0.58))
            key_rotation(p["body"], frame_end, (0.72, 0.88, 0.22))
        else:
            key_rotation(p["body"], frame_end, (0, 0, 0))
    elif clip == "celebrate":
        key_location(root, mid, ((start_x + end_x) / 2, depth, 0.18))
        key_rotation(p["l_shoulder"], q1, (1.95, -0.52, 0))
        key_rotation(p["r_shoulder"], q1, (1.95, 0.52, 0))
        key_rotation(p["l_shoulder"], mid, (2.30, -0.48, 0))
        key_rotation(p["r_shoulder"], mid, (2.30, 0.48, 0))
        key_rotation(p["head"], mid, (0, 0, 0.12))
        key_rotation(p["l_shoulder"], q3, (1.05, -0.22, 0))
        key_rotation(p["r_shoulder"], q3, (1.05, 0.22, 0))
    else:
        # Visible breathing / weight shift so "idle" is never a frozen cut-out.
        key_location(root, q1, (start_x, depth, 0.035))
        key_location(root, mid, ((start_x + end_x) / 2, depth, 0.0))
        key_location(root, q3, (end_x, depth, 0.03))
        key_rotation(p["body"], mid, (0.015, 0, -0.025 if facing == "left" else 0.025))
        key_rotation(p["head"], q1, (0.02, 0, -0.055 if facing == "left" else 0.055))
        key_rotation(p["head"], q3, (-0.015, 0, 0.04 if facing == "left" else -0.04))

    for obj in [root, *p.values()]:
        set_linear_interpolation(obj)


def create_power_effect(effect, rig, frame_end):
    effect = str(effect or "none").lower()
    if effect in {"", "none"}:
        return []

    root = rig["root"]
    mid = max(2, frame_end // 2)
    blue = new_material("PowerBlue", (0.07, 0.48, 1.0), roughness=0.22, emission=7.0, alpha=0.74)
    purple = new_material("PowerPurple", (0.55, 0.15, 1.0), roughness=0.22, emission=7.0, alpha=0.70)
    created = []

    if effect in {"energy_orb", "energy_blast", "lightning"}:
        orb = add_child_sphere("PowerOrb", root, (0.82, -0.48, 3.55), (0.15, 0.15, 0.15), blue, 24, 12)
        key_scale(orb, 1, (0.18, 0.18, 0.18))
        key_scale(orb, mid, (1.15, 1.15, 1.15))
        if effect == "energy_blast":
            key_location(orb, frame_end, (3.2, -0.48, 3.72))
            key_scale(orb, frame_end, (0.45, 0.45, 0.45))
        else:
            key_scale(orb, frame_end, (0.55, 0.55, 0.55))
        created.append(orb)
    elif effect == "shield":
        bubble = add_child_sphere("Shield", root, (0, 0, 2.75), (0.40, 0.34, 0.55), blue, 28, 14)
        key_scale(bubble, 1, (0.15, 0.15, 0.15))
        key_scale(bubble, mid, (3.0, 2.1, 4.7))
        key_scale(bubble, frame_end, (2.8, 2.0, 4.4))
        created.append(bubble)
    elif effect in {"shockwave", "kinetic_dash"}:
        ring = add_child_torus("Shockwave", root, (0, 0.18, 0.16), 0.58, 0.055, blue, (0, 0, 0))
        key_scale(ring, 1, (0.25, 0.25, 0.25))
        key_scale(ring, mid, (2.0, 2.0, 2.0))
        key_scale(ring, frame_end, (3.4, 3.4, 3.4))
        created.append(ring)
    elif effect == "portal":
        ring = add_child_torus(
            "Portal", root, (2.0, 1.1, 2.75), 0.95, 0.09, purple,
            (math.radians(90), 0, 0),
        )
        key_scale(ring, 1, (0.15, 0.15, 0.15))
        key_scale(ring, mid, (1.1, 1.1, 1.1))
        key_scale(ring, frame_end, (1.0, 1.0, 1.0))
        created.append(ring)
    elif effect == "telekinesis":
        for i, x in enumerate((-0.85, 0, 0.85)):
            cube = add_child_box(f"TeleProp{i}", root, (x, 0.8, 0.42), (0.34, 0.34, 0.34), purple, 0.05)
            key_location(cube, 1, (x, 0.8, 0.42))
            key_location(cube, mid, (x, 0.56, 2.45 + i * 0.18))
            key_location(cube, frame_end, (x * 1.12, 0.74, 2.05))
            created.append(cube)
    return created


def floor_color(text: str):
    t = str(text or "").lower()
    if any(x in t for x in ("forest", "grass", "garden", "outdoor", "field")):
        return (0.16, 0.26, 0.16)
    if any(x in t for x in ("ice", "snow", "water", "pool")):
        return (0.18, 0.26, 0.31)
    if any(x in t for x in ("hotel", "door", "wood", "hall", "room")):
        return (0.24, 0.19, 0.15)
    if any(x in t for x in ("lava", "fire", "cave")):
        return (0.22, 0.14, 0.11)
    if any(x in t for x in ("lab", "hospital", "school", "office")):
        return (0.27, 0.30, 0.33)
    return (0.22, 0.24, 0.28)


def build_stage(background_path: str | None, environment: str, shot_index: int = 0):
    """Build a real 3D foreground/midground around the researched environment plate."""
    env = str(environment or "Roblox game").lower()
    color = floor_color(environment)
    stage_root = add_empty("StageRoot")
    floor_mat = new_material("StageFloorMat", color, roughness=0.58)
    wall_color = tuple(min(1.0, max(0.035, c * 0.76 + 0.035)) for c in color)
    trim_color = tuple(min(1.0, max(0.05, c * 1.18 + 0.025)) for c in color)
    wall_mat = new_material("StageWallMat", wall_color, roughness=0.66)
    trim_mat = new_material("StageTrimMat", trim_color, roughness=0.48)
    dark_mat = new_material("StageDarkMat", tuple(max(0.025, c * 0.48) for c in color), roughness=0.72)

    # Large actual floor under the avatars. The backplate supplies game-specific
    # art while the 3D pieces below create perspective, shadows and parallax.
    add_child_box("StageFloor", stage_root, (0, 2.05, -0.11), (14.0, 10.2, 0.22), floor_mat, 0.04)

    if background_path:
        source = Path(str(background_path))
        if source.exists():
            image = bpy.data.images.load(str(source), check_existing=True)
            material = bpy.data.materials.new("GameEnvironmentPlate")
            material.use_nodes = True
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            nodes.clear()
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = image
            emission = nodes.new("ShaderNodeEmission")
            emission.inputs["Strength"].default_value = 0.86
            output = nodes.new("ShaderNodeOutputMaterial")
            links.new(tex.outputs["Color"], emission.inputs["Color"])
            links.new(emission.outputs["Emission"], output.inputs["Surface"])

            # Farther back than V5 originally used, leaving room for real 3D
            # midground geometry between the actors and image.
            bpy.ops.mesh.primitive_plane_add(
                location=(0, 7.35, 5.95),
                rotation=(math.radians(90), 0, 0),
            )
            plane = bpy.context.object
            plane.name = "GameEnvironmentBackplate"
            plane.scale = (6.35, 11.25, 1)
            # Slight deterministic offset means repeat visits to one location
            # do not look like the exact same crop every time.
            plane.location.x = ((shot_index % 3) - 1) * 0.22
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            plane.data.materials.append(material)

    variant = shot_index % 3

    # Camera-near framing pieces: intentionally off-centre so lateral camera
    # motion reveals depth instead of merely zooming a flat image.
    left_x = -5.15 + variant * 0.18
    right_x = 5.15 - ((variant + 1) % 3) * 0.14
    add_child_box("ForegroundLeft", stage_root, (left_x, 0.55, 1.55), (0.72, 2.0, 3.1), dark_mat, 0.10)
    add_child_box("ForegroundRight", stage_root, (right_x, 1.10, 1.35), (0.72, 2.4, 2.7), dark_mat, 0.10)

    # Environment-aware set dressing. These are architectural/readability
    # pieces only; gameplay-critical props still come from add_context_props().
    if any(word in env for word in ("hall", "hotel", "corridor", "room", "door")):
        for x in (-3.75, 3.75):
            add_child_box(f"HallWall{x}", stage_root, (x, 3.35, 2.2), (1.05, 5.0, 4.4), wall_mat, 0.07)
        for y in (1.8, 4.1):
            add_child_box(f"HallBeam{y}", stage_root, (0, y, 4.65), (7.4, 0.38, 0.35), trim_mat, 0.05)
    elif "library" in env:
        for x in (-3.85, 3.85):
            for y in (1.8, 3.7, 5.5):
                add_child_box(f"Shelf{x}_{y}", stage_root, (x, y, 1.65), (1.18, 0.60, 3.30), wall_mat, 0.05)
                for z in (0.72, 1.48, 2.24):
                    add_child_box(f"ShelfTrim{x}_{y}_{z}", stage_root, (x, y - 0.34, z), (1.06, 0.10, 0.12), trim_mat, 0.025)
    elif any(word in env for word in ("greenhouse", "forest", "garden", "woods")):
        for i, x in enumerate((-4.1, -3.1, 3.2, 4.15)):
            h = 1.6 + ((i + variant) % 3) * 0.45
            add_child_box(f"PlantStem{i}", stage_root, (x, 3.0 + (i % 2) * 1.4, h / 2), (0.22, 0.22, h), dark_mat, 0.10)
            add_child_sphere(f"PlantTop{i}", stage_root, (x, 3.0 + (i % 2) * 1.4, h + 0.45), (0.72, 0.58, 0.62), trim_mat, 18, 10)
    elif any(word in env for word in ("cave", "tunnel", "mine", "sewer")):
        for i, x in enumerate((-4.25, -3.25, 3.35, 4.3)):
            rock = add_child_box(f"RockColumn{i}", stage_root, (x, 3.0 + (i % 2) * 1.25, 1.35), (1.15, 1.00, 2.75), wall_mat, 0.24)
            rock.rotation_euler[2] = math.radians((-8 if i % 2 else 9) + variant * 2)
    elif any(word in env for word in ("street", "plaza", "city", "town")):
        for i, x in enumerate((-4.0, 4.0)):
            add_child_box(f"StreetPost{i}", stage_root, (x, 3.15, 1.55), (0.22, 0.22, 3.1), dark_mat, 0.06)
            add_child_box(f"StreetTop{i}", stage_root, (x, 3.15, 3.1), (0.85, 0.34, 0.34), trim_mat, 0.08)
        add_child_box("StreetBarrierL", stage_root, (-3.0, 4.7, 0.48), (2.1, 0.48, 0.80), wall_mat, 0.08)
        add_child_box("StreetBarrierR", stage_root, (3.0, 4.7, 0.48), (2.1, 0.48, 0.80), wall_mat, 0.08)
    elif any(word in env for word in ("obby", "tower", "platform", "parkour")):
        for i, (x, y, z) in enumerate(((-4.0, 3.3, 0.42), (3.8, 4.1, 0.78), (-3.3, 5.3, 1.10))):
            add_child_box(f"ObbyPlatform{i}", stage_root, (x, y, z), (2.1, 1.35, 0.34), trim_mat, 0.06)
    else:
        # Neutral game-architecture pieces for locations without a keyword match.
        add_child_box("MidLeft", stage_root, (-3.9, 4.0, 1.15), (1.2, 1.5, 2.3), wall_mat, 0.10)
        add_child_box("MidRight", stage_root, (3.9, 4.6, 1.45), (1.35, 1.5, 2.9), wall_mat, 0.10)
        add_child_box("MidTrim", stage_root, (0, 5.15, 4.45), (7.2, 0.38, 0.32), trim_mat, 0.05)


def add_context_props(shot, frame_end):
    text = " ".join(
        str(x or "")
        for x in (shot.get("action"), shot.get("environment"), shot.get("emotion"))
    ).lower()
    mid = max(2, frame_end // 2)
    q1 = max(2, frame_end // 4)
    props = []
    root = add_empty("ShotProps")
    neutral = new_material("PropNeutral", (0.24, 0.27, 0.32), roughness=0.52)
    gold = new_material("PropGold", (0.95, 0.68, 0.13), roughness=0.34, metallic=0.24)
    glow = new_material("PropGlow", (0.12, 0.72, 1.0), roughness=0.22, emission=3.0)

    if "door" in text or "closet" in text or "locker" in text:
        x = 2.4 if "left" not in text else -2.4
        hinge_sign = 1.0 if x > 0 else -1.0
        pivot = add_empty("StoryDoorPivot", root, (x + 0.775 * hinge_sign, 1.55, 2.15))
        door = add_child_box(
            "StoryDoor", pivot, (-0.775 * hinge_sign, 0.0, 0.0),
            (1.55, 0.30, 4.25), neutral, 0.08,
        )
        knob = add_child_sphere(
            "DoorKnob", pivot,
            (-1.22 * hinge_sign, -0.18, -0.10),
            (0.10, 0.08, 0.10), gold, 16, 8,
        )
        if any(word in text for word in ("open", "opened", "opening", "push", "escape", "enter")):
            key_rotation(pivot, 1, (0, 0, 0))
            key_rotation(pivot, q1, (0, 0, 0))
            key_rotation(pivot, mid, (0, 0, -1.05 * hinge_sign))
            key_rotation(pivot, frame_end, (0, 0, -1.18 * hinge_sign))
            set_linear_interpolation(pivot)
        props.extend([door, knob])

    if "key" in text:
        key_root = add_empty("StoryKeyRoot", root, (0.85, -0.10, 0.32))
        key = add_child_box("StoryKey", key_root, (0, 0, 0), (0.62, 0.12, 0.18), gold, 0.05)
        ring = add_child_torus("StoryKeyRing", key_root, (0.28, 0, 0), 0.18, 0.045, gold, (math.radians(90), 0, 0))
        if any(word in text for word in ("pickup", "pick up", "grab", "take", "collect")):
            key_location(key_root, 1, (0.85, -0.10, 0.32))
            key_location(key_root, mid, (0.35, -0.30, 1.25))
            key_location(key_root, frame_end, (0.20, -0.20, 2.10))
            key_rotation(key_root, mid, (0, 0.20, 0.35))
            set_linear_interpolation(key_root)
        props.extend([key, ring])

    if any(x in text for x in ("button", "switch", "lever")):
        console = add_child_box("StoryConsole", root, (-1.9, 0.75, 0.85), (0.95, 0.70, 1.50), neutral, 0.08)
        button = add_child_box("StoryButton", root, (-1.9, 0.34, 1.08), (0.36, 0.10, 0.36), glow, 0.05)
        if any(word in text for word in ("press", "push", "hit", "activate", "switch")):
            key_scale(button, 1, (1.0, 1.0, 1.0))
            key_scale(button, mid, (1.0, 0.42, 1.0))
            key_scale(button, frame_end, (1.0, 0.72, 1.0))
            set_linear_interpolation(button)
        props.extend([console, button])

    if any(x in text for x in ("chest", "crate", "loot", "box")):
        chest = add_child_box("StoryChest", root, (1.7, 0.55, 0.52), (1.30, 0.86, 0.90), neutral, 0.10)
        trim = add_child_box("StoryChestTrim", root, (1.7, 0.08, 0.55), (0.74, 0.05, 0.14), gold, 0.03)
        props.extend([chest, trim])

    if any(x in text for x in ("gem", "crystal", "coin", "rare item", "artifact")):
        item = add_child_sphere("StoryCollectible", root, (-0.90, 0.35, 0.48), (0.25, 0.18, 0.34), glow, 20, 10)
        if any(word in text for word in ("pickup", "pick up", "grab", "take", "collect")):
            key_location(item, 1, (-0.90, 0.35, 0.48))
            key_location(item, mid, (-0.45, -0.10, 1.45))
            key_location(item, frame_end, (0.0, -0.15, 2.25))
            key_scale(item, frame_end, (0.12, 0.12, 0.12))
            set_linear_interpolation(item)
        props.append(item)

    if "flashlight" in text:
        light = add_child_box("StoryFlashlight", root, (0.95, -0.12, 0.36), (0.20, 0.20, 0.76), neutral, 0.06)
        props.append(light)

    return props


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_camera(camera_name, motion, frame_end, focus_x=0.0, end_focus_x=None):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.name = "StoryCamera"
    bpy.context.scene.camera = cam

    presets = {
        "wide": ((focus_x, -11.8, 3.35), 48, 2.70),
        "medium": ((focus_x, -8.8, 3.55), 55, 3.15),
        "close-up": ((focus_x, -6.2, 4.15), 62, 4.05),
        "over-shoulder": ((focus_x - 1.10, -7.9, 3.70), 57, 3.35),
        "follow": ((focus_x, -9.0, 3.45), 52, 3.05),
        "low-angle": ((focus_x, -8.3, 2.15), 52, 3.20),
        "high-angle": ((focus_x, -9.2, 5.65), 55, 2.95),
    }
    loc, lens, target_z = presets.get(camera_name, presets["medium"])
    end_focus_x = focus_x if end_focus_x is None else float(end_focus_x)
    cam.location = loc
    cam.data.lens = lens
    cam.data.sensor_width = 32
    look_at(cam, (focus_x, 0, target_z))
    cam.keyframe_insert(data_path="location", frame=1)
    cam.keyframe_insert(data_path="rotation_euler", frame=1)

    end = Vector(loc)
    if motion == "push_in":
        end.y += 1.28
        end.x += (end_focus_x - focus_x) * 0.30
    elif motion == "pull_back":
        end.y -= 1.18
        end.x += (end_focus_x - focus_x) * 0.20
    elif motion == "track_left":
        end.x -= 1.30
    elif motion == "track_right":
        end.x += 1.30
    elif motion == "follow":
        end.x += (end_focus_x - focus_x) + 0.60
        end.y += 0.42
    elif motion == "small_orbit":
        end.x += 1.05
        end.y += 0.48
    elif motion == "reveal_pan":
        cam.location.x -= 1.20
        look_at(cam, (focus_x - 0.30, 0, target_z))
        cam.keyframe_insert(data_path="location", frame=1)
        cam.keyframe_insert(data_path="rotation_euler", frame=1)
        end.x = end_focus_x + 0.95

    # Mid-shot camera key makes movement feel authored rather than a single
    # mechanical A-to-B zoom.
    mid = max(2, frame_end // 2)
    start_vec = Vector(loc)
    mid_loc = start_vec.lerp(end, 0.52)
    if motion in {"small_orbit", "reveal_pan"}:
        mid_loc.y += 0.24
    cam.location = mid_loc
    look_at(cam, ((focus_x + end_focus_x) / 2, 0, target_z))
    cam.keyframe_insert(data_path="location", frame=mid)
    cam.keyframe_insert(data_path="rotation_euler", frame=mid)

    cam.location = end
    look_at(cam, (end_focus_x, 0, target_z))
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame_end)
    set_linear_interpolation(cam)
    return cam


def setup_lighting(environment: str):
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.065, 0.075, 0.105, 1)
        bg.inputs["Strength"].default_value = 0.62

    warm = any(x in str(environment or "").lower() for x in ("hotel", "wood", "fire", "sunset"))
    key_color = (1.0, 0.83, 0.68) if warm else (0.88, 0.93, 1.0)

    bpy.ops.object.light_add(type="AREA", location=(-4.0, -4.6, 7.9))
    key = bpy.context.object
    key.data.energy = 1050
    key.data.color = key_color
    key.data.shape = "DISK"
    key.data.size = 4.8
    look_at(key, (0, 0, 2.8))

    bpy.ops.object.light_add(type="AREA", location=(4.2, -1.0, 5.7))
    fill = bpy.context.object
    fill.data.energy = 630
    fill.data.color = (0.55, 0.70, 1.0)
    fill.data.size = 4.2
    look_at(fill, (0, 0, 3.0))

    bpy.ops.object.light_add(type="AREA", location=(0.0, 3.2, 6.5))
    rim = bpy.context.object
    rim.data.energy = 780
    rim.data.color = (0.70, 0.82, 1.0)
    rim.data.size = 3.3
    look_at(rim, (0, 0, 3.1))


def configure_scene(frame_end, frames_dir: Path):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"

    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 98
    scene.render.use_file_extension = True
    try:
        scene.render.image_settings.color_mode = "RGB"
    except Exception:
        pass
    scene.render.filepath = str(frames_dir / "frame_")
    # Prefer higher temporal sampling where the installed EEVEE API exposes it.
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        for attr, value in (("taa_render_samples", 128), ("taa_samples", 64)):
            if hasattr(eevee, attr):
                try:
                    setattr(eevee, attr, value)
                except Exception:
                    pass
    try:
        scene.render.film_transparent = False
    except Exception:
        pass
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


def render_shot(shot, output_dir: Path):
    clear_scene()
    duration = max(1.45, min(5.8, float(shot.get("duration") or 3.0)))
    frame_end = max(2, round(duration * FPS))
    environment = str(shot.get("environment") or shot.get("environment_key") or "Roblox game")

    build_stage(shot.get("background_path"), environment, int(shot.get("index") or 0))
    setup_lighting(environment)
    add_context_props(shot, frame_end)

    actors = shot.get("actors") or []
    start_lanes = []
    end_lanes = []
    for actor in actors:
        try:
            start_lane = float(actor.get("start_lane") or 0.0)
            end_lane = float(actor.get("end_lane") if actor.get("end_lane") is not None else start_lane)
            start_lanes.append(start_lane)
            end_lanes.append(end_lane)
        except Exception:
            pass
    focus_x = sum(start_lanes) / len(start_lanes) if start_lanes else 0.0
    end_focus_x = sum(end_lanes) / len(end_lanes) if end_lanes else focus_x
    setup_camera(
        str(shot.get("camera") or "medium"),
        str(shot.get("camera_motion") or "static"),
        frame_end,
        focus_x=focus_x,
        end_focus_x=end_focus_x,
    )

    render_actor_ids = []
    power_effects = []
    actor_count = max(1, len(actors))
    for actor_index, actor in enumerate(actors):
        cid = str(actor.get("id") or f"player{actor_index + 1}").lower()
        depth = actor_index * 0.10
        rig = build_avatar(cid, float(actor.get("start_lane") or 0.0), depth)
        animate_actor(actor, rig, frame_end, depth)
        effect = str(actor.get("power_effect") or "none")
        create_power_effect(effect, rig, frame_end)
        if effect not in {"", "none"}:
            power_effects.append(effect)
        render_actor_ids.append(cid)

    index = int(shot.get("index") or 0) + 1
    frames_dir = output_dir / f"scene_{index:02d}_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    configure_scene(frame_end, frames_dir)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(animation=True)

    report = {
        "renderer_version": "roblox_machinima_v5.2",
        "backend": "blender_roblox_machinima_v5",
        "frames_dir": str(frames_dir),
        "frame_pattern": "frame_%04d.jpg",
        "fps": FPS,
        "frames": frame_end,
        "rendered_frame_count": frame_end,
        "duration": round(frame_end / FPS, 3),
        "actor_count": len(actors),
        "actor_ids": render_actor_ids,
        "camera": shot.get("camera"),
        "camera_motion": shot.get("camera_motion"),
        "environment": environment,
        "power_effects": power_effects,
        "procedural_segmented_avatar": True,
        "ground_plane": True,
        "context_props": True,
    }
    (output_dir / f"scene_{index:02d}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main():
    args = parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shots = plan.get("shots") or []
    if not shots:
        raise SystemExit("Animation plan contains no shots.")

    for shot in shots:
        render_shot(shot, output_dir)


if __name__ == "__main__":
    main()
