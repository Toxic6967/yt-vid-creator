from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


FPS = 24


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def mat(name, color, *, emission=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes = m.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color[:3], 1)
        bsdf.inputs["Roughness"].default_value = 0.55
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if emission > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*color[:3], 1)
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = (*color[:3], 1)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission
    m.diffuse_color = (*color[:3], alpha)
    if alpha < 1:
        try:
            m.surface_render_method = "DITHERED"
        except Exception:
            try:
                m.blend_method = "BLEND"
            except Exception:
                pass
    return m


def add_box(name, loc, size, material, parent=None, bevel=0.08):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new(name="Roblox bevel", type="BEVEL")
        mod.width = bevel
        mod.segments = 3
    if parent:
        obj.parent = parent
    return obj


def add_uv(name, loc, scale, material, parent=None, segments=24, rings=12):
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
        obj.parent = parent
    return obj


def add_torus(name, loc, major, minor, material, parent=None, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=32,
        minor_segments=8,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def rgb(hex_value):
    value = hex_value.lstrip("#")
    return tuple(int(value[i:i+2], 16) / 255.0 for i in (0, 2, 4))


PALETTES = {
    "max": {
        "skin": rgb("#E1B47F"),
        "shirt": rgb("#2E63CB"),
        "pants": rgb("#252832"),
        "shoe": rgb("#F2F3F5"),
        "hair": rgb("#4A2E22"),
    },
    "mia": {
        "skin": rgb("#DCAA7E"),
        "shirt": rgb("#7D46BE"),
        "pants": rgb("#272933"),
        "shoe": rgb("#F0F0F3"),
        "hair": rgb("#2D2027"),
    },
    "kai": {
        "skin": rgb("#D3A276"),
        "shirt": rgb("#A83239"),
        "pants": rgb("#24262C"),
        "shoe": rgb("#B83238"),
        "hair": rgb("#1E1E22"),
    },
}


def create_r15(cid, lane):
    palette = PALETTES.get(cid, PALETTES["max"])
    mats = {k: mat(f"{cid}_{k}", v) for k, v in palette.items()}
    black = mat(f"{cid}_face", (0.035, 0.035, 0.04))
    root = bpy.data.objects.new(f"{cid}_ROOT", None)
    bpy.context.collection.objects.link(root)
    root.location = (lane, 0, 0)

    parts = {}
    parts["lower_torso"] = add_box(
        f"{cid}_LowerTorso", (0, 0, 2.55), (1.42, 0.70, 0.78), mats["shirt"], root, 0.10
    )
    parts["upper_torso"] = add_box(
        f"{cid}_UpperTorso", (0, 0, 3.35), (1.70, 0.74, 0.92), mats["shirt"], root, 0.11
    )
    parts["head"] = add_box(
        f"{cid}_Head", (0, 0, 4.55), (1.28, 1.02, 1.12), mats["skin"], root, 0.16
    )

    for side, sign in (("L", -1), ("R", 1)):
        x = 1.05 * sign
        parts[f"{side}_upper_arm"] = add_box(
            f"{cid}_{side}_UpperArm", (x, 0, 3.38), (0.42, 0.56, 0.84), mats["shirt"], root, 0.09
        )
        parts[f"{side}_lower_arm"] = add_box(
            f"{cid}_{side}_LowerArm", (x, 0, 2.70), (0.39, 0.52, 0.66), mats["skin"], root, 0.08
        )
        parts[f"{side}_hand"] = add_box(
            f"{cid}_{side}_Hand", (x, -0.01, 2.25), (0.42, 0.50, 0.30), mats["skin"], root, 0.10
        )
        # Rounded joint caps make the segmented body read as R15 rather than voxel/Minecraft.
        add_uv(
            f"{cid}_{side}_ShoulderJoint",
            (x, 0, 3.82),
            (0.22, 0.24, 0.22),
            mats["shirt"],
            root,
            16,
            8,
        )
        add_uv(
            f"{cid}_{side}_ElbowJoint",
            (x, 0, 3.02),
            (0.19, 0.20, 0.19),
            mats["skin"],
            root,
            16,
            8,
        )

        lx = 0.43 * sign
        parts[f"{side}_upper_leg"] = add_box(
            f"{cid}_{side}_UpperLeg", (lx, 0, 1.55), (0.58, 0.66, 0.86), mats["pants"], root, 0.09
        )
        parts[f"{side}_lower_leg"] = add_box(
            f"{cid}_{side}_LowerLeg", (lx, 0, 0.82), (0.54, 0.62, 0.64), mats["pants"], root, 0.08
        )
        parts[f"{side}_foot"] = add_box(
            f"{cid}_{side}_Foot", (lx, -0.10, 0.34), (0.62, 0.88, 0.32), mats["shoe"], root, 0.09
        )
        add_uv(
            f"{cid}_{side}_HipJoint",
            (lx, 0, 2.02),
            (0.24, 0.25, 0.22),
            mats["pants"],
            root,
            16,
            8,
        )
        add_uv(
            f"{cid}_{side}_KneeJoint",
            (lx, 0, 1.16),
            (0.21, 0.22, 0.19),
            mats["pants"],
            root,
            16,
            8,
        )

    # Small neck/joint separation is another strong R15 silhouette cue.
    add_uv(
        f"{cid}_NeckJoint",
        (0, 0, 4.02),
        (0.22, 0.22, 0.18),
        mats["skin"],
        root,
        16,
        8,
    )

    for x in (-0.22, 0.22):
        eye = add_uv(
            f"{cid}_Eye",
            (x, -0.515, 4.65),
            (0.055, 0.018, 0.085),
            black,
            root,
            16,
            8,
        )
        eye.rotation_euler[0] = math.radians(90)

    for x, z, rz in ((-0.14, 4.38, -0.22), (0, 4.32, 0), (0.14, 4.38, 0.22)):
        smile = add_box(
            f"{cid}_Smile",
            (x, -0.526, z),
            (0.16, 0.026, 0.045),
            black,
            root,
            0.015,
        )
        smile.rotation_euler[1] = rz

    # Character-specific catalog-hair silhouettes keep the recurring cast readable.
    if cid == "mia":
        for x, z, scale in (
            (-0.30, 5.13, (0.34, 0.48, 0.24)),
            (0.10, 5.20, (0.46, 0.50, 0.27)),
            (0.38, 5.05, (0.28, 0.42, 0.22)),
        ):
            add_uv(f"{cid}_Hair", (x, 0.02, z), scale, mats["hair"], root, 16, 8)
        for y, z, scale in (
            (0.52, 4.95, (0.24, 0.24, 0.30)),
            (0.68, 4.62, (0.22, 0.22, 0.34)),
            (0.76, 4.26, (0.19, 0.19, 0.31)),
        ):
            add_uv(f"{cid}_Ponytail", (0.34, y, z), scale, mats["hair"], root, 16, 8)
    elif cid == "kai":
        for x, z, scale in (
            (-0.30, 5.08, (0.31, 0.40, 0.18)),
            (0.02, 5.13, (0.39, 0.42, 0.20)),
            (0.32, 5.07, (0.29, 0.37, 0.17)),
        ):
            add_uv(f"{cid}_Hair", (x, 0, z), scale, mats["hair"], root, 16, 8)
    else:
        for x, z, scale in (
            (-0.38, 5.12, (0.34, 0.48, 0.24)),
            (0.0, 5.20, (0.45, 0.50, 0.28)),
            (0.36, 5.10, (0.32, 0.45, 0.25)),
            (-0.18, 5.30, (0.26, 0.34, 0.20)),
        ):
            add_uv(f"{cid}_Hair", (x, 0, z), scale, mats["hair"], root, 16, 8)

    # Simple clothing accents distinguish the cast without generating text/logos.
    if cid == "kai":
        accent = mat(f"{cid}_accent", rgb("#15171C"))
        add_box(f"{cid}_JacketStripe", (0, -0.39, 3.35), (0.34, 0.035, 0.76), accent, root, 0.015)
    elif cid == "mia":
        accent = mat(f"{cid}_accent", rgb("#E4D8FF"))
        add_box(f"{cid}_JacketZip", (0, -0.39, 3.35), (0.08, 0.035, 0.72), accent, root, 0.01)
    else:
        accent = mat(f"{cid}_accent", rgb("#173D8F"))
        add_box(f"{cid}_HoodiePocket", (0, -0.39, 3.10), (0.68, 0.035, 0.24), accent, root, 0.03)

    add_uv(
        f"{cid}_Shadow",
        (0, 0.22, 0.08),
        (0.72, 0.30, 0.045),
        mat(f"{cid}_shadow_mat", (0.03, 0.03, 0.035), alpha=0.30),
        root,
        20,
        8,
    )

    return {"root": root, "parts": parts}


def key(obj, frame, *, location=None, rotation=None, scale=None):
    if location is not None:
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation is not None:
        obj.rotation_euler = rotation
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def animate_actor(actor, rig, frame_end):
    root = rig["root"]
    parts = rig["parts"]
    clip = str(actor.get("clip") or "idle")
    start_x = float(actor.get("start_lane") or 0.0)
    end_x = float(actor.get("end_lane") if actor.get("end_lane") is not None else start_x)

    key(root, 1, location=(start_x, 0, 0))
    key(root, frame_end, location=(end_x, 0, 0))

    mid = max(2, frame_end // 2)
    q1 = max(2, frame_end // 4)
    q3 = max(q1 + 1, frame_end * 3 // 4)

    def swing(amount=0.65):
        for frame, sign in ((1, 1), (q1, -1), (mid, 1), (q3, -1), (frame_end, 1)):
            parts["L_upper_arm"].rotation_euler[0] = amount * sign
            parts["R_upper_arm"].rotation_euler[0] = -amount * sign
            parts["L_upper_leg"].rotation_euler[0] = -amount * sign
            parts["R_upper_leg"].rotation_euler[0] = amount * sign
            for name in ("L_upper_arm", "R_upper_arm", "L_upper_leg", "R_upper_leg"):
                parts[name].keyframe_insert(data_path="rotation_euler", frame=frame)

    if clip in {"run", "dash"}:
        swing(0.80 if clip == "run" else 1.0)
        key(root, mid, location=((start_x + end_x) / 2, 0, 0.10))
    elif clip == "walk":
        swing(0.42)
    elif clip == "jump":
        key(root, 1, location=(start_x, 0, 0))
        key(root, mid, location=((start_x + end_x) / 2, 0, 1.15))
        key(root, frame_end, location=(end_x, 0, 0))
    elif clip in {"crouch", "hide"}:
        key(root, mid, location=((start_x + end_x) / 2, 0, -0.65))
        key(root, frame_end, location=(end_x, 0, -0.48 if clip == "hide" else 0))
    elif clip in {"react", "look_back", "turn"}:
        key(root, 1, rotation=(0, 0, 0))
        key(root, mid, rotation=(0, 0, math.radians(18 if clip != "turn" else 42)))
        key(root, frame_end, rotation=(0, 0, 0 if clip != "turn" else math.radians(28)))
    elif clip == "point":
        parts["R_upper_arm"].rotation_euler[0] = math.radians(-75)
        parts["R_lower_arm"].rotation_euler[0] = math.radians(-25)
        parts["R_upper_arm"].keyframe_insert(data_path="rotation_euler", frame=mid)
        parts["R_lower_arm"].keyframe_insert(data_path="rotation_euler", frame=mid)
    elif clip in {"open", "push", "pickup"}:
        parts["R_upper_arm"].rotation_euler[0] = math.radians(-65)
        parts["R_lower_arm"].rotation_euler[0] = math.radians(-45)
        parts["R_upper_arm"].keyframe_insert(data_path="rotation_euler", frame=mid)
        parts["R_lower_arm"].keyframe_insert(data_path="rotation_euler", frame=mid)
        if clip == "pickup":
            key(root, mid, location=((start_x + end_x) / 2, 0, -0.35))
    elif clip in {"attack", "power_cast", "ground_slam", "shield"}:
        parts["R_upper_arm"].rotation_euler[0] = math.radians(-95)
        parts["L_upper_arm"].rotation_euler[0] = math.radians(-55)
        parts["R_upper_arm"].keyframe_insert(data_path="rotation_euler", frame=q1)
        parts["L_upper_arm"].keyframe_insert(data_path="rotation_euler", frame=q1)
        parts["R_upper_arm"].rotation_euler[0] = math.radians(35)
        parts["L_upper_arm"].rotation_euler[0] = math.radians(20)
        parts["R_upper_arm"].keyframe_insert(data_path="rotation_euler", frame=mid)
        parts["L_upper_arm"].keyframe_insert(data_path="rotation_euler", frame=mid)
        if clip == "ground_slam":
            key(root, q1, location=(start_x, 0, 0.65))
            key(root, mid, location=((start_x + end_x) / 2, 0, -0.08))
    elif clip in {"fall", "stumble"}:
        key(root, 1, rotation=(0, 0, 0))
        key(root, mid, rotation=(math.radians(12), 0, math.radians(18)))
        if clip == "fall":
            key(root, frame_end, location=(end_x, 0, -1.15), rotation=(math.radians(75), 0, math.radians(10)))
        else:
            key(root, frame_end, rotation=(0, 0, 0))
    elif clip == "celebrate":
        for name in ("L_upper_arm", "R_upper_arm"):
            parts[name].rotation_euler[0] = math.radians(-145)
            parts[name].keyframe_insert(data_path="rotation_euler", frame=mid)
        key(root, mid, location=((start_x + end_x) / 2, 0, 0.18))
    else:
        key(root, mid, location=((start_x + end_x) / 2, 0, 0.07))


def create_power_effect(effect, rig, frame_end):
    if not effect or effect == "none":
        return
    root = rig["root"]
    glow_blue = mat("PowerBlue", (0.10, 0.55, 1.0), emission=8.0, alpha=0.70)
    glow_purple = mat("PowerPurple", (0.58, 0.18, 1.0), emission=7.0, alpha=0.65)
    mid = max(2, frame_end // 2)

    if effect in {"energy_orb", "energy_blast", "lightning"}:
        orb = add_uv("PowerOrb", (0.95, -0.35, 2.65), (0.10, 0.10, 0.10), glow_blue, root, 20, 10)
        key(orb, 1, scale=(0.05, 0.05, 0.05))
        key(orb, mid, scale=(0.42, 0.42, 0.42))
        if effect == "energy_blast":
            key(orb, frame_end, location=(3.6, -0.2, 2.9), scale=(0.18, 0.18, 0.18))
        else:
            key(orb, frame_end, scale=(0.18, 0.18, 0.18))
    elif effect == "shield":
        bubble = add_uv("Shield", (0, 0, 2.6), (0.3, 0.3, 0.3), glow_blue, root, 28, 14)
        key(bubble, 1, scale=(0.25, 0.25, 0.25))
        key(bubble, mid, scale=(2.0, 1.35, 2.55))
        key(bubble, frame_end, scale=(1.85, 1.25, 2.35))
    elif effect in {"shockwave", "kinetic_dash"}:
        ring = add_torus("Shockwave", (0, 0, 0.18), 0.7, 0.07, glow_blue, root)
        key(ring, 1, scale=(0.25, 0.25, 0.25))
        key(ring, mid, scale=(1.9, 1.9, 1.9))
        key(ring, frame_end, scale=(3.1, 3.1, 3.1))
    elif effect == "portal":
        ring = add_torus(
            "Portal",
            (1.8, 0.8, 2.5),
            1.05,
            0.11,
            glow_purple,
            None,
            rotation=(math.radians(90), 0, 0),
        )
        key(ring, 1, scale=(0.2, 0.2, 0.2))
        key(ring, mid, scale=(1.25, 1.25, 1.25))
        key(ring, frame_end, scale=(1.05, 1.05, 1.05))
    elif effect == "telekinesis":
        for i, x in enumerate((-1.1, 0.0, 1.1)):
            cube = add_box(
                f"TelekineticProp{i}",
                (x, 1.2, 0.55),
                (0.45, 0.45, 0.45),
                glow_purple,
                None,
                0.05,
            )
            key(cube, mid, location=(x * 0.8, 1.0, 2.0 + i * 0.25))
            key(cube, frame_end, location=(x * 1.1, 1.2, 1.5))


def background_plate(path):
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    try:
        image = bpy.data.images.load(str(p), check_existing=True)
        material = bpy.data.materials.new("EnvironmentPlate")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = 0.85
        out = nodes.new("ShaderNodeOutputMaterial")
        links.new(tex.outputs["Color"], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], out.inputs["Surface"])

        bpy.ops.mesh.primitive_plane_add(location=(0, 5.2, 4.4), rotation=(math.radians(90), 0, 0))
        plane = bpy.context.object
        plane.name = "EnvironmentBackplate"
        plane.scale = (5.9, 10.5, 1)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        plane.data.materials.append(material)
    except Exception:
        pass


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_camera(camera_name, motion, frame_end):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.name = "StoryCamera"
    bpy.context.scene.camera = cam

    presets = {
        "wide": ((0, -13.5, 4.4), 40),
        "medium": ((0, -10.2, 4.0), 48),
        "close-up": ((0, -7.5, 4.2), 58),
        "over-shoulder": ((-1.6, -8.8, 4.0), 50),
        "follow": ((0, -10.8, 3.8), 46),
        "low-angle": ((0, -9.4, 2.35), 45),
        "high-angle": ((0, -10.5, 6.5), 48),
    }
    loc, lens = presets.get(camera_name, presets["medium"])
    cam.location = loc
    cam.data.lens = lens
    look_at(cam, (0, 0, 2.8))
    cam.keyframe_insert(data_path="location", frame=1)
    cam.keyframe_insert(data_path="rotation_euler", frame=1)

    end_loc = Vector(loc)
    if motion == "push_in":
        end_loc.y += 1.2
    elif motion == "pull_back":
        end_loc.y -= 1.2
    elif motion == "track_left":
        end_loc.x -= 1.3
    elif motion == "track_right":
        end_loc.x += 1.3
    elif motion == "follow":
        end_loc.x += 0.8
        end_loc.y += 0.45
    elif motion == "small_orbit":
        end_loc.x += 1.2
        end_loc.y += 0.6
    elif motion == "reveal_pan":
        cam.location.x -= 1.1
        cam.keyframe_insert(data_path="location", frame=1)
        end_loc.x = 1.1

    cam.location = end_loc
    look_at(cam, (0, 0, 2.8))
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame_end)


def setup_lighting():
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.03, 0.035, 0.05, 1)
        bg.inputs["Strength"].default_value = 0.35

    bpy.ops.object.light_add(type="AREA", location=(-4.0, -3.5, 8.0))
    key_light = bpy.context.object
    key_light.data.energy = 1100
    key_light.data.shape = "DISK"
    key_light.data.size = 5.0
    look_at(key_light, (0, 0, 2.8))

    bpy.ops.object.light_add(type="AREA", location=(4.5, 1.0, 6.0))
    rim = bpy.context.object
    rim.data.energy = 800
    rim.data.color = (0.45, 0.62, 1.0)
    rim.data.size = 4.0
    look_at(rim, (0, 0, 3.0))


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
    try:
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    except Exception:
        pass
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(output)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


def render_shot(shot, output_dir):
    clear_scene()
    duration = max(1.3, min(6.5, float(shot.get("duration") or 3.0)))
    frame_end = max(2, round(duration * FPS))
    setup_lighting()
    background_plate(shot.get("background_path"))
    setup_camera(
        str(shot.get("camera") or "medium"),
        str(shot.get("camera_motion") or "static"),
        frame_end,
    )

    for actor in shot.get("actors") or []:
        cid = str(actor.get("id") or "max").lower()
        rig = create_r15(cid, float(actor.get("start_lane") or 0.0))
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

    for shot in plan.get("shots") or []:
        render_shot(shot, output_dir)


if __name__ == "__main__":
    main()
