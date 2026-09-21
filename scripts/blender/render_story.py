from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector


FPS = 24
TARGET_AVATAR_HEIGHT = 5.4


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--r15-template", required=True)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def rgb(hex_value: str):
    value = hex_value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


PALETTES = {
    "max": {
        "skin": rgb("#E2B584"),
        "shirt": rgb("#2864D7"),
        "pants": rgb("#202630"),
        "shoe": rgb("#F4F5F7"),
        "hair": rgb("#4B3023"),
        "accent": rgb("#173D8F"),
    },
    "mia": {
        "skin": rgb("#DDAA7E"),
        "shirt": rgb("#8149C7"),
        "pants": rgb("#252733"),
        "shoe": rgb("#F1F1F4"),
        "hair": rgb("#2C2028"),
        "accent": rgb("#E4D8FF"),
    },
    "kai": {
        "skin": rgb("#D5A377"),
        "shirt": rgb("#B33740"),
        "pants": rgb("#20232B"),
        "shoe": rgb("#C53A43"),
        "hair": rgb("#1D1D22"),
        "accent": rgb("#11151B"),
    },
}


def new_material(name, color, *, emission=0.0, alpha=1.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = (*color[:3], 1)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.52
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if emission > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*color[:3], 1)
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = (*color[:3], 1)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission
    material.diffuse_color = (*color[:3], alpha)
    if alpha < 1:
        try:
            material.surface_render_method = "DITHERED"
        except Exception:
            try:
                material.blend_method = "BLEND"
            except Exception:
                pass
    return material


def add_uv(name, loc, scale, material, parent=None, segments=20, rings=10):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=loc,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if parent:
        parent_keep_world(obj, parent)
    return obj


def add_box(name, loc, size, material, parent=None, bevel=0.05):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new(name="SoftRobloxEdge", type="BEVEL")
        mod.width = bevel
        mod.segments = 2
    if parent:
        parent_keep_world(obj, parent)
    return obj


def add_torus(name, loc, major, minor, material, parent=None, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=36,
        minor_segments=10,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    if parent:
        parent_keep_world(obj, parent)
    return obj


def parent_keep_world(obj, parent):
    matrix = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = matrix


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def object_bounds(objects):
    points = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        try:
            evaluated = obj.evaluated_get(depsgraph)
            points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
        except Exception:
            points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return (-1, 1, -0.5, 0.5, 0, TARGET_AVATAR_HEIGHT)
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def set_mesh_material(obj, material):
    if obj.type != "MESH":
        return
    if len(obj.data.materials):
        for index in range(len(obj.data.materials)):
            obj.data.materials[index] = material
    else:
        obj.data.materials.append(material)


def classify_body_material(name: str, mats):
    key = norm(name)
    if any(x in key for x in ("cage", "attachment", "attgeo", "facial", "lash", "brow")):
        return None
    if any(x in key for x in ("uppertorso", "lowertorso", "torso")):
        return mats["shirt"]
    if any(x in key for x in ("upperleg", "lowerleg", "leg")):
        return mats["pants"]
    if any(x in key for x in ("foot", "shoe")):
        return mats["shoe"]
    if any(x in key for x in ("head", "upperarm", "lowerarm", "hand", "arm")):
        return mats["skin"]
    return None


def find_pose_bone(armature, candidates):
    if not armature or armature.type != "ARMATURE":
        return None
    normalized = {norm(bone.name): bone for bone in armature.pose.bones}
    for candidate in candidates:
        target = norm(candidate)
        if target in normalized:
            return normalized[target]
    for candidate in candidates:
        target = norm(candidate)
        for key, bone in normalized.items():
            if key.endswith(target) or target in key:
                return bone
    return None


def key_rotation(bone, frame, xyz):
    if not bone:
        return
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = xyz
    bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def key_object(obj, frame, *, location=None, rotation=None, scale=None):
    if location is not None:
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation is not None:
        obj.rotation_euler = rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def import_official_r15(cid: str, lane: float, template_path: Path):
    if not template_path.exists():
        raise RuntimeError(f"Official Roblox R15 template is missing: {template_path}")

    before = {obj.name for obj in bpy.context.scene.objects}
    bpy.ops.import_scene.fbx(filepath=str(template_path), use_anim=False)
    imported = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    if not imported:
        raise RuntimeError("Blender imported no objects from the official Roblox R15 FBX.")

    imported_names = {obj.name for obj in imported}
    for obj in imported:
        low = obj.name.lower()
        if "cage" in low or "attachment" in low or low.endswith("_att"):
            obj.hide_render = True
            obj.hide_viewport = True

    armatures = [obj for obj in imported if obj.type == "ARMATURE" and not obj.hide_render]
    armature = armatures[0] if armatures else None
    if armature and armature.animation_data:
        armature.animation_data_clear()

    meshes = [obj for obj in imported if obj.type == "MESH" and not obj.hide_render]
    if not meshes:
        raise RuntimeError("Official Roblox R15 FBX contains no visible body meshes.")

    root = bpy.data.objects.new(f"{cid}_OFFICIAL_R15_ROOT", None)
    bpy.context.collection.objects.link(root)
    top_level = [
        obj for obj in imported
        if obj.parent is None or obj.parent.name not in imported_names
    ]
    for obj in top_level:
        parent_keep_world(obj, root)

    bpy.context.view_layer.update()
    min_x, max_x, min_y, max_y, min_z, max_z = object_bounds(meshes)
    height = max(0.01, max_z - min_z)
    uniform = TARGET_AVATAR_HEIGHT / height
    root.scale = (uniform, uniform, uniform)
    root.location = (lane, 0, -min_z * uniform)
    bpy.context.view_layer.update()

    palette = PALETTES.get(cid, PALETTES["max"])
    mats = {
        key: new_material(f"{cid}_{key}", color)
        for key, color in palette.items()
    }
    for obj in meshes:
        material = classify_body_material(obj.name, mats)
        if material:
            set_mesh_material(obj, material)

    # Recalculate final bounds after normalization.
    min_x, max_x, min_y, max_y, min_z, max_z = object_bounds(meshes)
    center_x = (min_x + max_x) / 2
    front_y = min_y - 0.015
    head_height = max_z - min_z
    head_z = min_z + head_height * 0.86
    width = max_x - min_x

    # Guaranteed classic Roblox-readable face aimed toward our camera.
    face_mat = new_material(f"{cid}_classic_face", (0.025, 0.025, 0.03))
    eye_dx = max(0.09, width * 0.07)
    for ex in (center_x - eye_dx, center_x + eye_dx):
        eye = add_uv(
            f"{cid}_ClassicEye",
            (ex, front_y, head_z + head_height * 0.025),
            (0.045, 0.014, 0.070),
            face_mat,
            root,
            16,
            8,
        )
        eye.rotation_euler[0] = math.radians(90)
    for dx, dz, tilt in (
        (-0.10, -0.08, -0.20),
        (0.0, -0.11, 0.0),
        (0.10, -0.08, 0.20),
    ):
        mouth = add_box(
            f"{cid}_ClassicSmile",
            (center_x + dx, front_y - 0.008, head_z + dz),
            (0.12, 0.022, 0.032),
            face_mat,
            root,
            0.01,
        )
        mouth.rotation_euler[1] = tilt

    # Simple recurring catalog-hair silhouettes; body geometry itself is Roblox official.
    hair_z = max_z + 0.03
    if cid == "mia":
        for xoff, zoff, scale in (
            (-0.20, 0.00, (0.25, 0.23, 0.16)),
            (0.04, 0.05, (0.31, 0.24, 0.17)),
            (0.25, -0.01, (0.22, 0.21, 0.15)),
        ):
            add_uv(f"{cid}_Hair", (center_x + xoff, (min_y + max_y)/2, hair_z + zoff), scale, mats["hair"], root)
        for yoff, zoff, scale in (
            (0.28, -0.15, (0.18, 0.17, 0.22)),
            (0.42, -0.38, (0.16, 0.15, 0.24)),
        ):
            add_uv(f"{cid}_Ponytail", (center_x + 0.20, max_y + yoff, hair_z + zoff), scale, mats["hair"], root)
    elif cid == "kai":
        for xoff, zoff, scale in (
            (-0.18, 0.00, (0.22, 0.20, 0.12)),
            (0.02, 0.04, (0.27, 0.21, 0.13)),
            (0.21, 0.00, (0.20, 0.19, 0.12)),
        ):
            add_uv(f"{cid}_Hair", (center_x + xoff, (min_y + max_y)/2, hair_z + zoff), scale, mats["hair"], root)
    else:
        for xoff, zoff, scale in (
            (-0.25, 0.00, (0.24, 0.23, 0.16)),
            (-0.03, 0.08, (0.31, 0.25, 0.18)),
            (0.24, 0.02, (0.23, 0.22, 0.15)),
        ):
            add_uv(f"{cid}_Hair", (center_x + xoff, (min_y + max_y)/2, hair_z + zoff), scale, mats["hair"], root)

    # Soft screen-space grounding shadow.
    shadow_mat = new_material(f"{cid}_shadow", (0.015, 0.015, 0.02), alpha=0.22)
    add_uv(
        f"{cid}_GroundShadow",
        (lane, 0.25, 0.08),
        (0.72, 0.30, 0.045),
        shadow_mat,
        root,
        20,
        8,
    )

    return {
        "root": root,
        "armature": armature,
        "meshes": meshes,
        "bounds": (min_x, max_x, min_y, max_y, min_z, max_z),
    }


def animate_actor(actor, rig, frame_end):
    root = rig["root"]
    arm = rig.get("armature")
    clip = str(actor.get("clip") or "idle")
    start_x = float(actor.get("start_lane") or 0.0)
    end_x = float(actor.get("end_lane") if actor.get("end_lane") is not None else start_x)
    base_z = root.location.z
    q1 = max(2, frame_end // 4)
    mid = max(2, frame_end // 2)
    q3 = max(q1 + 1, frame_end * 3 // 4)

    key_object(root, 1, location=(start_x, 0, base_z), rotation=(0, 0, 0))
    key_object(root, frame_end, location=(end_x, 0, base_z))

    bones = {
        "lua": find_pose_bone(arm, ("LeftUpperArm", "LeftShoulder")),
        "rua": find_pose_bone(arm, ("RightUpperArm", "RightShoulder")),
        "lla": find_pose_bone(arm, ("LeftLowerArm", "LeftElbow")),
        "rla": find_pose_bone(arm, ("RightLowerArm", "RightElbow")),
        "lul": find_pose_bone(arm, ("LeftUpperLeg", "LeftHip")),
        "rul": find_pose_bone(arm, ("RightUpperLeg", "RightHip")),
        "lll": find_pose_bone(arm, ("LeftLowerLeg", "LeftKnee")),
        "rll": find_pose_bone(arm, ("RightLowerLeg", "RightKnee")),
        "torso": find_pose_bone(arm, ("UpperTorso", "LowerTorso", "Torso")),
        "head": find_pose_bone(arm, ("Head",)),
    }

    def walk_cycle(amount):
        for frame, sign in ((1, 1), (q1, -1), (mid, 1), (q3, -1), (frame_end, 1)):
            key_rotation(bones["lua"], frame, (amount * sign, 0, 0))
            key_rotation(bones["rua"], frame, (-amount * sign, 0, 0))
            key_rotation(bones["lul"], frame, (-amount * 0.72 * sign, 0, 0))
            key_rotation(bones["rul"], frame, (amount * 0.72 * sign, 0, 0))
            key_rotation(bones["lll"], frame, (max(0, amount * 0.28 * sign), 0, 0))
            key_rotation(bones["rll"], frame, (max(0, -amount * 0.28 * sign), 0, 0))

    if clip in {"walk", "run", "dash"}:
        walk_cycle(0.24 if clip == "walk" else (0.38 if clip == "run" else 0.48))
        bob = 0.08 if clip == "walk" else 0.13
        key_object(root, q1, location=(start_x + (end_x-start_x)*0.25, 0, base_z + bob))
        key_object(root, mid, location=(start_x + (end_x-start_x)*0.50, 0, base_z))
        key_object(root, q3, location=(start_x + (end_x-start_x)*0.75, 0, base_z + bob))
    elif clip == "jump":
        key_object(root, mid, location=((start_x + end_x)/2, 0, base_z + 1.05))
        key_rotation(bones["lua"], mid, (-0.45, 0, 0))
        key_rotation(bones["rua"], mid, (-0.45, 0, 0))
    elif clip in {"crouch", "hide"}:
        key_object(root, mid, location=((start_x + end_x)/2, 0, base_z - 0.48))
        key_object(root, frame_end, location=(end_x, 0, base_z - (0.34 if clip == "hide" else 0.12)))
        key_rotation(bones["torso"], mid, (0.16, 0, 0))
    elif clip in {"react", "look_back", "turn"}:
        angle = 0.20 if clip != "turn" else 0.45
        key_object(root, mid, rotation=(0, 0, angle))
        key_object(root, frame_end, rotation=(0, 0, 0 if clip != "turn" else angle * 0.65))
        key_rotation(bones["head"], mid, (0, 0, -0.20 if clip == "look_back" else 0.12))
    elif clip == "point":
        key_rotation(bones["rua"], q1, (-0.72, 0, -0.08))
        key_rotation(bones["rla"], q1, (-0.24, 0, 0))
        key_rotation(bones["rua"], frame_end, (-0.62, 0, -0.08))
    elif clip in {"open", "push", "pickup"}:
        key_rotation(bones["rua"], mid, (-0.62, 0, 0))
        key_rotation(bones["rla"], mid, (-0.48, 0, 0))
        if clip == "pickup":
            key_object(root, mid, location=((start_x + end_x)/2, 0, base_z - 0.30))
            key_rotation(bones["torso"], mid, (0.28, 0, 0))
    elif clip in {"attack", "power_cast", "ground_slam", "shield"}:
        key_rotation(bones["rua"], q1, (-0.78, 0, -0.10))
        key_rotation(bones["lua"], q1, (-0.48, 0, 0.10))
        key_rotation(bones["rua"], mid, (0.28, 0, 0))
        key_rotation(bones["lua"], mid, (0.18, 0, 0))
        if clip == "ground_slam":
            key_object(root, q1, location=(start_x, 0, base_z + 0.55))
            key_object(root, mid, location=((start_x+end_x)/2, 0, base_z - 0.05))
    elif clip in {"fall", "stumble"}:
        key_object(root, mid, rotation=(0.16, 0, 0.22))
        if clip == "fall":
            key_object(root, frame_end, location=(end_x, 0, base_z - 0.65), rotation=(0.85, 0, 0.20))
        else:
            key_object(root, frame_end, rotation=(0, 0, 0))
    elif clip == "celebrate":
        key_rotation(bones["lua"], mid, (-1.25, 0, 0))
        key_rotation(bones["rua"], mid, (-1.25, 0, 0))
        key_object(root, mid, location=((start_x+end_x)/2, 0, base_z + 0.15))
    else:
        key_object(root, mid, location=((start_x+end_x)/2, 0, base_z + 0.035))


def create_power_effect(effect, rig, frame_end):
    if not effect or effect == "none":
        return
    root = rig["root"]
    min_x, max_x, min_y, max_y, min_z, max_z = rig["bounds"]
    chest_z = min_z + (max_z-min_z) * 0.60
    front_y = min_y - 0.30
    mid = max(2, frame_end // 2)
    glow_blue = new_material("PowerBlue", (0.08, 0.50, 1.0), emission=7.0, alpha=0.72)
    glow_purple = new_material("PowerPurple", (0.55, 0.15, 1.0), emission=7.0, alpha=0.68)

    if effect in {"energy_orb", "energy_blast", "lightning"}:
        orb = add_uv(
            "PowerOrb",
            (max_x + 0.35, front_y, chest_z),
            (0.08, 0.08, 0.08),
            glow_blue,
            root,
            20,
            10,
        )
        key_object(orb, 1, scale=(0.25, 0.25, 0.25))
        key_object(orb, mid, scale=(1.0, 1.0, 1.0))
        if effect == "energy_blast":
            key_object(orb, frame_end, location=(max_x + 2.8, front_y, chest_z + 0.20), scale=(0.45, 0.45, 0.45))
        else:
            key_object(orb, frame_end, scale=(0.55, 0.55, 0.55))
    elif effect == "shield":
        bubble = add_uv(
            "Shield",
            ((min_x+max_x)/2, 0, min_z + (max_z-min_z)*0.48),
            (0.30, 0.30, 0.30),
            glow_blue,
            root,
            28,
            14,
        )
        key_object(bubble, 1, scale=(0.15, 0.15, 0.15))
        key_object(bubble, mid, scale=(4.7, 3.0, 5.9))
        key_object(bubble, frame_end, scale=(4.3, 2.8, 5.4))
    elif effect in {"shockwave", "kinetic_dash"}:
        ring = add_torus(
            "Shockwave",
            ((min_x+max_x)/2, 0, min_z + 0.12),
            0.55,
            0.055,
            glow_blue,
            root,
        )
        key_object(ring, 1, scale=(0.30, 0.30, 0.30))
        key_object(ring, mid, scale=(2.0, 2.0, 2.0))
        key_object(ring, frame_end, scale=(3.2, 3.2, 3.2))
    elif effect == "portal":
        ring = add_torus(
            "Portal",
            (max_x + 1.1, 0.8, chest_z),
            0.85,
            0.09,
            glow_purple,
            None,
            rotation=(math.radians(90), 0, 0),
        )
        key_object(ring, 1, scale=(0.15, 0.15, 0.15))
        key_object(ring, mid, scale=(1.15, 1.15, 1.15))
        key_object(ring, frame_end, scale=(1.0, 1.0, 1.0))
    elif effect == "telekinesis":
        for index, xoff in enumerate((-0.9, 0, 0.9)):
            cube = add_box(
                f"TelekineticProp{index}",
                ((min_x+max_x)/2 + xoff, 0.7, min_z + 0.45),
                (0.34, 0.34, 0.34),
                glow_purple,
                None,
                0.04,
            )
            key_object(cube, 1, location=(cube.location.x, 0.7, min_z + 0.45))
            key_object(cube, mid, location=(cube.location.x, 0.55, chest_z + index * 0.22))
            key_object(cube, frame_end, location=(cube.location.x + xoff*0.25, 0.65, chest_z - 0.15))


def background_plate(path):
    if not path:
        return
    source = Path(path)
    if not source.exists():
        return

    image = bpy.data.images.load(str(source), check_existing=True)
    material = bpy.data.materials.new("RobloxEnvironmentPlate")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 0.95
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])

    bpy.ops.mesh.primitive_plane_add(
        location=(0, 3.6, 5.0),
        rotation=(math.radians(90), 0, 0),
    )
    plane = bpy.context.object
    plane.name = "RobloxEnvironmentBackplate"
    plane.scale = (5.1, 9.1, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    plane.data.materials.append(material)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_camera(camera_name, motion, frame_end):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.name = "StoryCamera"
    bpy.context.scene.camera = cam
    presets = {
        "wide": ((0, -12.2, 3.7), 46),
        "medium": ((0, -9.5, 3.6), 52),
        "close-up": ((0, -7.2, 4.0), 62),
        "over-shoulder": ((-1.35, -8.7, 3.7), 54),
        "follow": ((0, -10.0, 3.5), 50),
        "low-angle": ((0, -8.8, 2.25), 50),
        "high-angle": ((0, -9.8, 5.8), 54),
    }
    loc, lens = presets.get(camera_name, presets["medium"])
    cam.location = loc
    cam.data.lens = lens
    look_at(cam, (0, 0, 2.7))
    cam.keyframe_insert(data_path="location", frame=1)
    cam.keyframe_insert(data_path="rotation_euler", frame=1)

    end = Vector(loc)
    if motion == "push_in":
        end.y += 0.85
    elif motion == "pull_back":
        end.y -= 0.85
    elif motion == "track_left":
        end.x -= 0.85
    elif motion == "track_right":
        end.x += 0.85
    elif motion == "follow":
        end.x += 0.55
        end.y += 0.35
    elif motion == "small_orbit":
        end.x += 0.75
        end.y += 0.30
    elif motion == "reveal_pan":
        cam.location.x -= 0.8
        cam.keyframe_insert(data_path="location", frame=1)
        end.x = 0.8

    cam.location = end
    look_at(cam, (0, 0, 2.7))
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame_end)


def setup_lighting():
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.055, 0.065, 0.09, 1)
        bg.inputs["Strength"].default_value = 0.45

    bpy.ops.object.light_add(type="AREA", location=(-4.0, -4.2, 7.8))
    key_light = bpy.context.object
    key_light.data.energy = 950
    key_light.data.shape = "DISK"
    key_light.data.size = 4.5
    look_at(key_light, (0, 0, 2.8))

    bpy.ops.object.light_add(type="AREA", location=(4.2, -0.4, 5.8))
    fill = bpy.context.object
    fill.data.energy = 650
    fill.data.color = (0.58, 0.70, 1.0)
    fill.data.size = 4.0
    look_at(fill, (0, 0, 2.8))


def configure_scene(frame_end, output):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"

    scene.render.resolution_x = 720
    scene.render.resolution_y = 1280
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(output)
    try:
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    except Exception:
        pass
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


def render_shot(shot, output_dir, template_path):
    clear_scene()
    duration = max(1.3, min(6.5, float(shot.get("duration") or 3.0)))
    frame_end = max(2, round(duration * FPS))

    background_plate(shot.get("background_path"))
    setup_lighting()
    setup_camera(
        str(shot.get("camera") or "medium"),
        str(shot.get("camera_motion") or "static"),
        frame_end,
    )

    for actor in shot.get("actors") or []:
        cid = str(actor.get("id") or "max").lower()
        rig = import_official_r15(
            cid,
            float(actor.get("start_lane") or 0.0),
            template_path,
        )
        animate_actor(actor, rig, frame_end)
        create_power_effect(str(actor.get("power_effect") or "none"), rig, frame_end)

    index = int(shot.get("index") or 0) + 1
    output = output_dir / f"scene_{index:02d}.mp4"
    configure_scene(frame_end, output)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(animation=True)


def main():
    args = parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    template_path = Path(args.r15_template)

    if not template_path.exists():
        raise SystemExit(f"Official Roblox R15 template missing: {template_path}")

    for shot in plan.get("shots") or []:
        render_shot(shot, output_dir, template_path)


if __name__ == "__main__":
    main()
