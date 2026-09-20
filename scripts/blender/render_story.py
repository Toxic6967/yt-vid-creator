from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector


FPS = 30
RENDERER_VERSION = "3.3-cinematic-r15"


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
        bsdf.inputs["Roughness"].default_value = 0.40
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.46
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.32
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


def add_tapered_box(name, loc, *, top_width, bottom_width, depth, height, material, parent=None, bevel=0.08):
    """R15-style tapered torso block: game-like, but not a Minecraft cube."""
    z0 = -height / 2
    z1 = height / 2
    td = depth / 2
    verts = [
        (-bottom_width/2,-td,z0),(bottom_width/2,-td,z0),
        (bottom_width/2,td,z0),(-bottom_width/2,td,z0),
        (-top_width/2,-td,z1),(top_width/2,-td,z1),
        (top_width/2,td,z1),(-top_width/2,td,z1),
    ]
    faces = [
        (0,1,2,3),(4,7,6,5),
        (0,4,5,1),(1,5,6,2),
        (2,6,7,3),(4,0,3,7),
    ]
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj = bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new(name="R15 bevel",type="BEVEL")
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


def add_empty(name, loc, parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    if parent:
        obj.parent = parent
    return obj


def reparent_keep_world(obj, parent):
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world


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
    parts["lower_torso"] = add_tapered_box(
        f"{cid}_LowerTorso",
        (0,0,2.55),
        top_width=1.44,
        bottom_width=1.24,
        depth=0.70,
        height=0.78,
        material=mats["shirt"],
        parent=root,
        bevel=0.10,
    )
    parts["upper_torso"] = add_tapered_box(
        f"{cid}_UpperTorso",
        (0,0,3.35),
        top_width=1.76,
        bottom_width=1.48,
        depth=0.74,
        height=0.92,
        material=mats["shirt"],
        parent=root,
        bevel=0.11,
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
        parts[f"{side}_shoulder_joint"] = add_uv(
            f"{cid}_{side}_ShoulderJoint",
            (x, 0, 3.82),
            (0.22, 0.24, 0.22),
            mats["shirt"],
            root,
            16,
            8,
        )
        parts[f"{side}_elbow_joint"] = add_uv(
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
        parts[f"{side}_hip_joint"] = add_uv(
            f"{cid}_{side}_HipJoint",
            (lx, 0, 2.02),
            (0.24, 0.25, 0.22),
            mats["pants"],
            root,
            16,
            8,
        )
        parts[f"{side}_knee_joint"] = add_uv(
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

    for eye_index, x in enumerate((-0.22,0.22)):
        eye = add_uv(
            f"{cid}_Eye_{eye_index}",
            (x,-0.515,4.65),
            (0.055,0.018,0.085),
            black,
            root,
            16,
            8,
        )
        eye.rotation_euler[0] = math.radians(90)
        parts[f"eye_{eye_index}"] = eye

    for smile_index, (x,z,rz) in enumerate(((-0.14,4.38,-0.22),(0,4.32,0),(0.14,4.38,0.22))):
        smile = add_box(
            f"{cid}_Smile_{smile_index}",
            (x,-0.526,z),
            (0.16,0.026,0.045),
            black,
            root,
            0.015,
        )
        smile.rotation_euler[1] = rz
        parts[f"smile_{smile_index}"] = smile

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

    # Simple hierarchical controls make limb motion pivot at Roblox joints
    # instead of rotating disconnected blocks around their centres.
    controls = {}
    for side, sign in (("L", -1), ("R", 1)):
        shoulder = add_empty(f"{cid}_{side}_Shoulder_CTRL", (1.05 * sign, 0, 3.82), root)
        elbow = add_empty(f"{cid}_{side}_Elbow_CTRL", (1.05 * sign, 0, 3.02), root)
        reparent_keep_world(elbow, shoulder)
        for name in (f"{side}_upper_arm",):
            reparent_keep_world(parts[name], shoulder)
        for name in (f"{side}_lower_arm", f"{side}_hand", f"{side}_elbow_joint"):
            reparent_keep_world(parts[name], elbow)
        controls[f"{side}_shoulder"] = shoulder
        controls[f"{side}_elbow"] = elbow

        hip = add_empty(f"{cid}_{side}_Hip_CTRL", (0.43 * sign, 0, 2.02), root)
        knee = add_empty(f"{cid}_{side}_Knee_CTRL", (0.43 * sign, 0, 1.16), root)
        reparent_keep_world(knee, hip)
        reparent_keep_world(parts[f"{side}_upper_leg"], hip)
        for name in (f"{side}_lower_leg", f"{side}_foot", f"{side}_knee_joint"):
            reparent_keep_world(parts[name], knee)
        controls[f"{side}_hip"] = hip
        controls[f"{side}_knee"] = knee

    # Upper-body controls give the character weight, eye-line and reactions.
    spine = add_empty(f"{cid}_Spine_CTRL", (0, 0, 2.92), root)
    reparent_keep_world(parts["upper_torso"], spine)
    for obj in list(bpy.data.objects):
        if not obj.name.startswith(f"{cid}_"):
            continue
        if any(token in obj.name for token in ("HoodiePocket", "JacketStripe", "JacketZip")):
            reparent_keep_world(obj, spine)

    head = add_empty(f"{cid}_Head_CTRL", (0, 0, 4.02), spine)
    for obj in list(bpy.data.objects):
        if not obj.name.startswith(f"{cid}_"):
            continue
        if any(token in obj.name for token in ("Head", "Eye", "Smile", "Hair", "Ponytail", "NeckJoint")):
            if obj not in {head, spine}:
                reparent_keep_world(obj, head)

    controls["spine"] = spine
    controls["head"] = head
    return {"root": root, "parts": parts, "controls": controls}


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


def smooth_curves(*objects):
    """Use clean eased curves instead of robotic linear keyframes."""
    for obj in objects:
        action = getattr(getattr(obj, "animation_data", None), "action", None)
        if not action:
            continue
        for fcurve in action.fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = "BEZIER"
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"


def add_point_light(name, loc, color, energy=650.0, parent=None):
    data = bpy.data.lights.new(name=name, type="POINT")
    data.energy = energy
    data.color = color[:3]
    data.shadow_soft_size = 1.2
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    if parent:
        obj.parent = parent
    return obj


def animate_actor(actor, rig, frame_end):
    root = rig["root"]
    controls = rig.get("controls") or {}
    clip = str(actor.get("clip") or "idle")
    emotion = str(actor.get("emotion") or "").lower()
    start_x = float(actor.get("start_lane") or 0.0)
    end_x = float(actor.get("end_lane") if actor.get("end_lane") is not None else start_x)
    facing = -1.0 if str(actor.get("facing") or "right").lower() == "left" else 1.0
    base_yaw = math.radians(7.0 * facing)

    mid = max(2, frame_end // 2)
    q1 = max(2, frame_end // 4)
    q3 = max(q1 + 1, frame_end * 3 // 4)

    key(root, 1, location=(start_x, 0, 0), rotation=(0, 0, base_yaw))
    key(root, frame_end, location=(end_x, 0, 0), rotation=(0, 0, base_yaw))
    key(controls["spine"], 1, rotation=(0, 0, 0))
    key(controls["head"], 1, rotation=(0, 0, 0))
    key(controls["spine"], frame_end, rotation=(0, 0, 0))
    key(controls["head"], frame_end, rotation=(0, 0, 0))

    def locomotion(*, stride, cycles, bounce, lean):
        steps = max(4, cycles * 2 + 1)
        for i in range(steps):
            t = i / (steps - 1)
            frame = 1 + round((frame_end - 1) * t)
            sign = 1 if i % 2 == 0 else -1
            x = start_x + (end_x - start_x) * t
            z = bounce if i % 2 else 0.0
            key(root, frame, location=(x, 0, z), rotation=(0, 0, base_yaw))
            key(controls["spine"], frame, rotation=(lean, 0, math.radians(-2.5 * sign)))
            key(controls["head"], frame, rotation=(math.radians(-lean * 10), 0, math.radians(2.0 * sign)))
            controls["L_shoulder"].rotation_euler[0] = stride * sign
            controls["R_shoulder"].rotation_euler[0] = -stride * sign
            controls["L_hip"].rotation_euler[0] = -stride * 0.78 * sign
            controls["R_hip"].rotation_euler[0] = stride * 0.78 * sign
            controls["L_knee"].rotation_euler[0] = max(0.0, -stride * 0.42 * sign)
            controls["R_knee"].rotation_euler[0] = max(0.0, stride * 0.42 * sign)
            controls["L_elbow"].rotation_euler[0] = max(0.0, -stride * 0.24 * sign)
            controls["R_elbow"].rotation_euler[0] = max(0.0, stride * 0.24 * sign)
            for name in (
                "L_shoulder","R_shoulder","L_hip","R_hip",
                "L_knee","R_knee","L_elbow","R_elbow",
            ):
                controls[name].keyframe_insert(data_path="rotation_euler", frame=frame)

    if clip == "run":
        locomotion(stride=math.radians(48), cycles=4, bounce=0.10, lean=math.radians(9))
    elif clip == "walk":
        locomotion(stride=math.radians(26), cycles=3, bounce=0.045, lean=math.radians(3))
    elif clip == "dash":
        locomotion(stride=math.radians(58), cycles=3, bounce=0.07, lean=math.radians(15))
        key(root, q1, scale=(0.96, 1.0, 1.04))
        key(root, mid, scale=(1.05, 1.0, 0.95))
        key(root, frame_end, scale=(1, 1, 1))
    elif clip == "stop":
        key(controls["spine"], 1, rotation=(math.radians(10), 0, 0))
        key(controls["spine"], mid, rotation=(math.radians(-7), 0, 0))
        key(controls["spine"], frame_end, rotation=(0, 0, 0))
        key(root, mid, location=(start_x + (end_x-start_x)*0.8, 0, 0.04))
    elif clip == "jump":
        key(root, q1, location=(start_x + (end_x-start_x)*0.22, 0, 0.22))
        key(root, mid, location=((start_x + end_x) / 2, 0, 1.18))
        key(root, q3, location=(start_x + (end_x-start_x)*0.82, 0, 0.28))
        key(root, frame_end, location=(end_x, 0, 0))
        for name in ("L_shoulder","R_shoulder"):
            key(controls[name], q1, rotation=(math.radians(-55),0,0))
            key(controls[name], mid, rotation=(math.radians(-105),0,0))
            key(controls[name], frame_end, rotation=(0,0,0))
        key(controls["spine"], mid, rotation=(math.radians(-8),0,0))
    elif clip in {"crouch", "hide"}:
        key(root, q1, location=(start_x, 0, -0.18))
        key(root, mid, location=((start_x + end_x) / 2, 0, -0.58))
        key(root, frame_end, location=(end_x, 0, -0.45 if clip == "hide" else 0))
        key(controls["spine"], mid, rotation=(math.radians(13),0,0))
        key(controls["head"], mid, rotation=(math.radians(-7),0,math.radians(8*facing)))
        for side in ("L","R"):
            key(controls[f"{side}_hip"], mid, rotation=(math.radians(38),0,0))
            key(controls[f"{side}_knee"], mid, rotation=(math.radians(-55),0,0))
    elif clip in {"react", "look_back", "turn"}:
        turn_amount = 22 if clip == "react" else (48 if clip == "look_back" else 62)
        key(controls["spine"], q1, rotation=(math.radians(-5),0,math.radians(turn_amount*0.35*facing)))
        key(controls["head"], q1, rotation=(math.radians(-4),0,math.radians(turn_amount*facing)))
        key(controls["head"], mid, rotation=(math.radians(2),0,math.radians(turn_amount*0.82*facing)))
        if clip == "turn":
            key(root, frame_end, rotation=(0,0,base_yaw + math.radians(48*facing)))
        else:
            key(controls["head"], frame_end, rotation=(0,0,0))
        for name in ("L_shoulder","R_shoulder"):
            key(controls[name], mid, rotation=(math.radians(-28),0,0))
    elif clip == "point":
        key(controls["R_shoulder"], q1, rotation=(math.radians(-35),0,math.radians(-8)))
        key(controls["R_shoulder"], mid, rotation=(math.radians(-82),0,math.radians(-8)))
        key(controls["R_elbow"], mid, rotation=(math.radians(-14),0,0))
        key(controls["head"], mid, rotation=(0,0,math.radians(-10)))
    elif clip in {"open", "push", "pickup"}:
        key(controls["spine"], q1, rotation=(math.radians(6),0,0))
        key(controls["R_shoulder"], mid, rotation=(math.radians(-72),0,0))
        key(controls["R_elbow"], mid, rotation=(math.radians(-48),0,0))
        if clip == "pickup":
            key(root, mid, location=((start_x + end_x)/2,0,-0.34))
            key(controls["spine"], mid, rotation=(math.radians(20),0,0))
    elif clip in {"attack", "power_cast", "ground_slam", "shield"}:
        key(controls["spine"], q1, rotation=(math.radians(-9),0,math.radians(-4*facing)))
        key(controls["head"], q1, rotation=(math.radians(3),0,math.radians(4*facing)))
        key(controls["R_shoulder"], q1, rotation=(math.radians(-105),0,math.radians(-15)))
        key(controls["L_shoulder"], q1, rotation=(math.radians(-62),0,math.radians(12)))
        key(controls["R_elbow"], q1, rotation=(math.radians(-42),0,0))
        if clip == "ground_slam":
            key(root, q1, location=(start_x,0,0.62))
            key(root, mid, location=((start_x + end_x)/2,0,-0.08))
            key(controls["spine"], mid, rotation=(math.radians(22),0,0))
            key(controls["R_shoulder"], mid, rotation=(math.radians(28),0,0))
            key(controls["L_shoulder"], mid, rotation=(math.radians(28),0,0))
        elif clip == "shield":
            key(controls["R_shoulder"], mid, rotation=(math.radians(-70),0,math.radians(-35)))
            key(controls["L_shoulder"], mid, rotation=(math.radians(-70),0,math.radians(35)))
        else:
            key(controls["R_shoulder"], mid, rotation=(math.radians(-25),0,math.radians(-8)))
            key(controls["L_shoulder"], mid, rotation=(math.radians(-20),0,math.radians(8)))
    elif clip in {"fall", "stumble"}:
        key(controls["spine"], q1, rotation=(math.radians(14),0,math.radians(10*facing)))
        key(root, mid, rotation=(math.radians(9),0,base_yaw + math.radians(16*facing)))
        if clip == "fall":
            key(root, frame_end, location=(end_x,0,-1.10), rotation=(math.radians(78),0,math.radians(10*facing)))
        else:
            key(root, frame_end, rotation=(0,0,base_yaw))
            key(controls["spine"], frame_end, rotation=(0,0,0))
    elif clip == "celebrate":
        for name in ("L_shoulder","R_shoulder"):
            key(controls[name], q1, rotation=(math.radians(-85),0,0))
            key(controls[name], mid, rotation=(math.radians(-148),0,0))
        key(root, q1, location=(start_x,0,0.05))
        key(root, mid, location=((start_x+end_x)/2,0,0.24))
        key(root, frame_end, location=(end_x,0,0))
        key(controls["head"], mid, rotation=(math.radians(-8),0,0))
    else:
        # Breathing/weight shift so even a quiet shot never looks frozen.
        key(root, q1, location=(start_x,0,0.025))
        key(root, mid, location=((start_x+end_x)/2,0,0.055))
        key(root, q3, location=(end_x,0,0.025))
        key(controls["spine"], q1, rotation=(math.radians(-1.5),0,math.radians(-2)))
        key(controls["spine"], q3, rotation=(math.radians(1.5),0,math.radians(2)))
        key(controls["head"], mid, rotation=(math.radians(-2),0,math.radians(3*facing)))

    # Emotion adds subtle acting without changing the planned action.
    if any(word in emotion for word in ("scared","panic","nervous","worried")):
        key(controls["head"], q3, rotation=(math.radians(-5),0,math.radians(9*facing)))
        key(controls["spine"], q3, rotation=(math.radians(-6),0,math.radians(-4*facing)))
    elif any(word in emotion for word in ("angry","determined","focused")):
        key(controls["head"], q3, rotation=(math.radians(3),0,0))
        key(controls["spine"], q3, rotation=(math.radians(7),0,0))
    elif any(word in emotion for word in ("sad","defeated")):
        key(controls["head"], q3, rotation=(math.radians(10),0,0))
        key(controls["spine"], q3, rotation=(math.radians(6),0,0))

    # One subtle blink gives close-ups life without turning the classic Roblox
    # face into a human facial-animation system.
    blink_frame = max(4,min(frame_end-3,round(frame_end*0.34)))
    for eye_name in ("eye_0","eye_1"):
        eye = rig["parts"].get(eye_name)
        if not eye:
            continue
        key(eye,blink_frame-2,scale=(1,1,1))
        key(eye,blink_frame,scale=(1,1,0.12))
        key(eye,blink_frame+2,scale=(1,1,1))
        smooth_curves(eye)

    smooth_curves(root,*controls.values())

def create_power_effect(effect, rig, frame_end):
    if not effect or effect == "none":
        return
    root = rig["root"]
    glow_blue = mat("PowerBlue", (0.08, 0.48, 1.0), emission=12.0, alpha=0.66)
    glow_cyan = mat("PowerCyan", (0.10, 0.95, 1.0), emission=14.0, alpha=0.58)
    glow_purple = mat("PowerPurple", (0.62, 0.16, 1.0), emission=12.0, alpha=0.62)
    mid = max(2, frame_end // 2)
    q1 = max(2, frame_end // 4)
    q3 = max(q1 + 1, frame_end * 3 // 4)

    if effect in {"energy_orb", "energy_blast"}:
        orb = add_uv("PowerOrb", (0.98, -0.42, 2.72), (0.08, 0.08, 0.08), glow_cyan, root, 28, 14)
        light = add_point_light("PowerOrbLight", (0.98,-0.42,2.72), (0.1,0.65,1.0), 250, root)
        key(orb, 1, scale=(0.05,0.05,0.05))
        key(orb, q1, scale=(0.24,0.24,0.24))
        key(orb, mid, scale=(0.52,0.52,0.52))
        light.data.energy = 250
        light.data.keyframe_insert(data_path="energy", frame=1)
        light.data.energy = 1150
        light.data.keyframe_insert(data_path="energy", frame=mid)
        if effect == "energy_blast":
            beam = add_box("EnergyBeam", (1.95,-0.42,2.72), (0.20,0.16,0.16), glow_blue, root, 0.06)
            key(beam, q1, scale=(0.05,1,1))
            key(beam, mid, scale=(8.0,1.0,1.0))
            key(beam, q3, scale=(10.5,0.65,0.65))
            key(beam, frame_end, scale=(0.05,0.05,0.05))
            key(orb, q3, location=(3.6,-0.42,2.72), scale=(0.18,0.18,0.18))
        else:
            key(orb, frame_end, scale=(0.18,0.18,0.18))
        smooth_curves(orb)
    elif effect == "lightning":
        for i in range(7):
            x = 0.72 + i * 0.42
            z = 2.75 + (0.18 if i % 2 else -0.10)
            bolt = add_box(
                f"Lightning_{i}",
                (x,-0.40,z),
                (0.48,0.055,0.055),
                glow_cyan,
                root,
                0.025,
            )
            bolt.rotation_euler[1] = math.radians(18 if i % 2 else -16)
            key(bolt, q1, scale=(0.05,0.05,0.05))
            key(bolt, mid, scale=(1,1,1))
            key(bolt, q3, scale=(0.55,0.55,0.55))
            key(bolt, frame_end, scale=(0.03,0.03,0.03))
        add_point_light("LightningLight", (1.8,-0.4,2.8), (0.2,0.8,1.0), 1250, root)
    elif effect == "shield":
        bubble = add_uv("Shield", (0,0,2.7), (0.3,0.3,0.3), glow_blue, root, 36, 18)
        key(bubble, 1, scale=(0.20,0.20,0.20))
        key(bubble, q1, scale=(1.25,0.95,1.60))
        key(bubble, mid, scale=(1.85,1.35,2.45))
        key(bubble, frame_end, scale=(1.70,1.25,2.30))
        add_point_light("ShieldLight", (0,-0.2,3.0), (0.15,0.55,1.0), 700, root)
        smooth_curves(bubble)
    elif effect == "shockwave":
        for ring_index in range(3):
            ring = add_torus(
                f"Shockwave_{ring_index}",
                (0,0,0.16 + ring_index*0.035),
                0.55 + ring_index*0.18,
                0.055,
                glow_cyan,
                root,
            )
            start = min(frame_end-1, mid + ring_index*2)
            key(ring, start, scale=(0.15,0.15,0.15))
            key(ring, min(frame_end, start+8), scale=(2.1,2.1,2.1))
            key(ring, frame_end, scale=(3.4,3.4,3.4))
            smooth_curves(ring)
        add_point_light("ShockwaveLight", (0,0,0.45), (0.15,0.65,1.0), 900, root)
    elif effect == "kinetic_dash":
        for i in range(6):
            trail = add_uv(
                f"DashTrail_{i}",
                (-0.28-i*0.32,0.20,2.6),
                (0.18,0.08,0.55),
                glow_blue,
                root,
                16,
                8,
            )
            key(trail, 1, scale=(0.02,0.02,0.02))
            key(trail, mid, scale=(1.0,1.0,1.0))
            key(trail, frame_end, scale=(0.12,0.12,0.12))
        add_point_light("DashLight", (0,-0.2,2.8), (0.1,0.55,1.0), 850, root)
    elif effect == "portal":
        ring = add_torus(
            "Portal",
            (1.8,0.8,2.6),
            1.08,
            0.115,
            glow_purple,
            None,
            rotation=(math.radians(90),0,0),
        )
        inner = add_uv("PortalCore", (1.8,0.82,2.6), (0.12,0.12,0.12), glow_purple, None, 28, 14)
        key(ring, 1, scale=(0.15,0.15,0.15))
        key(ring, mid, scale=(1.28,1.28,1.28))
        key(ring, frame_end, scale=(1.06,1.06,1.06))
        key(inner, 1, scale=(0.05,0.05,0.05))
        key(inner, mid, scale=(6.8,1.0,6.8))
        key(inner, frame_end, scale=(5.9,1.0,5.9))
        ring.rotation_euler[2] = 0
        ring.keyframe_insert(data_path="rotation_euler", frame=1)
        ring.rotation_euler[2] = math.radians(130)
        ring.keyframe_insert(data_path="rotation_euler", frame=frame_end)
        add_point_light("PortalLight", (1.8,0.0,2.6), (0.65,0.2,1.0), 1100)
        smooth_curves(ring, inner)
    elif effect == "telekinesis":
        for i, x in enumerate((-1.1,0.0,1.1)):
            cube = add_box(
                f"TelekineticProp{i}",
                (x,1.2,0.55),
                (0.45,0.45,0.45),
                glow_purple,
                None,
                0.05,
            )
            key(cube, 1, location=(x,1.2,0.55), rotation=(0,0,0))
            key(cube, mid, location=(x*0.8,1.0,2.0+i*0.25), rotation=(0.3*i,0.4,0.6*i))
            key(cube, frame_end, location=(x*1.1,1.2,1.5), rotation=(0.8,0.5*i,1.2))
            smooth_curves(cube)
        add_point_light("TelekinesisLight", (0,0.2,2.5), (0.65,0.2,1.0), 900)

def _sample_lower_image_color(image):
    try:
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            raise ValueError
        samples = []
        for xr in (0.35,0.50,0.65):
            x = min(width-1, max(0, int(width*xr)))
            y = min(height-1, max(0, int(height*0.13)))
            index = (y*width+x)*4
            pixels = image.pixels[index:index+3]
            samples.append(tuple(float(v) for v in pixels))
        return tuple(sum(sample[i] for sample in samples)/len(samples) for i in range(3))
    except Exception:
        return (0.12,0.13,0.16)


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
        tex.interpolation = "Linear"
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = 0.82
        out = nodes.new("ShaderNodeOutputMaterial")
        links.new(tex.outputs["Color"], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], out.inputs["Surface"])

        bpy.ops.mesh.primitive_plane_add(location=(0,5.5,4.8), rotation=(math.radians(90),0,0))
        plane = bpy.context.object
        plane.name = "EnvironmentBackplate"
        plane.scale = (6.4,11.4,1)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        plane.data.materials.append(material)

        # A colour-matched ground plane receives proper character/power shadows
        # and prevents the actors from looking pasted onto a flat image.
        floor_color = _sample_lower_image_color(image)
        floor_mat = mat("EnvironmentFloor", floor_color)
        floor_bsdf = floor_mat.node_tree.nodes.get("Principled BSDF")
        if floor_bsdf:
            floor_bsdf.inputs["Roughness"].default_value = 0.78
        bpy.ops.mesh.primitive_plane_add(size=28, location=(0,1.5,-0.03))
        floor = bpy.context.object
        floor.name = "EnvironmentGround"
        floor.data.materials.append(floor_mat)
    except Exception:
        pass

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_camera(camera_name, motion, frame_end, *, target_x=0.0, high_energy=False):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.name = "StoryCamera"
    bpy.context.scene.camera = cam

    presets = {
        "wide": ((0,-13.8,4.5), 39),
        "medium": ((0,-10.4,4.0), 50),
        "close-up": ((0,-7.4,4.35), 64),
        "over-shoulder": ((-1.7,-8.9,4.1), 54),
        "follow": ((0,-10.9,3.8), 47),
        "low-angle": ((0,-9.5,2.45), 46),
        "high-angle": ((0,-10.8,6.7), 50),
    }
    loc, lens = presets.get(camera_name, presets["medium"])
    start_loc = Vector((loc[0] + target_x*0.20, loc[1], loc[2]))
    target = Vector((target_x,0,2.75))

    focus = add_empty("CameraFocus", target)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = focus
    cam.data.dof.aperture_fstop = 4.6 if camera_name != "close-up" else 3.4

    cam.location = start_loc
    cam.data.lens = lens
    look_at(cam, target)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.keyframe_insert(data_path="rotation_euler", frame=1)
    cam.data.keyframe_insert(data_path="lens", frame=1)

    end_loc = Vector(start_loc)
    end_lens = lens
    if motion == "push_in":
        end_loc.y += 1.15
        end_lens += 2.0
    elif motion == "pull_back":
        end_loc.y -= 1.25
        end_lens -= 1.5
    elif motion == "track_left":
        end_loc.x -= 1.25
    elif motion == "track_right":
        end_loc.x += 1.25
    elif motion == "follow":
        end_loc.x += 0.85
        end_loc.y += 0.42
    elif motion == "small_orbit":
        end_loc.x += 1.15
        end_loc.y += 0.62
    elif motion == "reveal_pan":
        cam.location.x -= 1.05
        cam.keyframe_insert(data_path="location", frame=1)
        end_loc.x += 1.05

    cam.location = end_loc
    cam.data.lens = end_lens
    look_at(cam, target)
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame_end)
    cam.data.keyframe_insert(data_path="lens", frame=frame_end)

    if high_energy and frame_end > 12:
        impact = max(5, frame_end//2)
        impact_t = max(0.0, min(1.0, impact / max(1, frame_end)))
        base = start_loc.lerp(end_loc, impact_t)
        for offset, dx, dz in ((-3,-0.035,0.025),(-1,0.045,-0.020),(1,-0.025,0.018),(3,0.018,-0.012)):
            frame = max(2,min(frame_end-1,impact+offset))
            cam.location = base + Vector((dx,0,dz))
            look_at(cam,target)
            cam.keyframe_insert(data_path="location",frame=frame)
            cam.keyframe_insert(data_path="rotation_euler",frame=frame)
        cam.location = end_loc

    smooth_curves(cam)
    return cam

def setup_lighting(*, role="build", powered=False):
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.018,0.022,0.035,1)
        bg.inputs["Strength"].default_value = 0.28

    bpy.ops.object.light_add(type="AREA", location=(-4.2,-3.8,8.2))
    key_light = bpy.context.object
    key_light.name = "KeyLight"
    key_light.data.energy = 1250 if role in {"hook","reveal","payoff"} else 1050
    key_light.data.shape = "DISK"
    key_light.data.size = 5.2
    key_light.data.color = (1.0,0.87,0.72)
    look_at(key_light,(0,0,2.7))

    bpy.ops.object.light_add(type="AREA", location=(4.4,-1.0,5.6))
    fill = bpy.context.object
    fill.name = "FillLight"
    fill.data.energy = 500
    fill.data.size = 4.5
    fill.data.color = (0.52,0.68,1.0)
    look_at(fill,(0,0,2.8))

    bpy.ops.object.light_add(type="AREA", location=(3.8,2.6,7.0))
    rim = bpy.context.object
    rim.name = "RimLight"
    rim.data.energy = 950 if powered else 680
    rim.data.color = (0.20,0.55,1.0) if powered else (0.42,0.58,1.0)
    rim.data.size = 3.2
    look_at(rim,(0,0,3.0))

def configure_scene(frame_end, output, *, powered=False):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"

    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1920
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.film_transparent = False

    try:
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = 0.35
    except Exception:
        pass
    try:
        scene.eevee.taa_render_samples = 64
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 3
        scene.eevee.gtao_factor = 1.15
    except Exception:
        pass

    # Compositor glow gives powers a polished game-VFX bloom without asking AI
    # video to hallucinate the effect frame by frame.
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    render_layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 0.8 if powered else 2.8
    glare.size = 6
    composite = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(render_layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], composite.inputs["Image"])

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.audio_codec = "NONE"
    try:
        scene.render.ffmpeg.constant_rate_factor = "HIGH"
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
        scene.render.ffmpeg.video_bitrate = 14000
    except Exception:
        pass

    # Blender's movie renderer may append its own extension depending on build/settings.
    # Render to an extension-free stem, then normalise the emitted movie ourselves.
    scene.render.use_file_extension = True
    scene.render.filepath = str(Path(output).with_suffix(""))

    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

def render_shot(shot, output_dir):
    clear_scene()
    duration = max(1.3,min(6.5,float(shot.get("duration") or 3.0)))
    frame_end = max(2,round(duration*FPS))
    power_effects = [
        str(actor.get("power_effect") or "none")
        for actor in (shot.get("actors") or [])
    ]
    powered = any(effect != "none" for effect in power_effects)
    role = str(shot.get("role") or "build")

    background_plate(shot.get("background_path"))
    setup_lighting(role=role,powered=powered)

    actors = shot.get("actors") or []
    target_x = (
        sum(
            (float(actor.get("start_lane") or 0.0)+float(actor.get("end_lane") or actor.get("start_lane") or 0.0))/2
            for actor in actors
        ) / len(actors)
        if actors else 0.0
    )
    setup_camera(
        str(shot.get("camera") or "medium"),
        str(shot.get("camera_motion") or "static"),
        frame_end,
        target_x=target_x,
        high_energy=powered or role in {"reveal","payoff"},
    )

    for actor in actors:
        cid = str(actor.get("id") or "max").lower()
        rig = create_r15(cid,float(actor.get("start_lane") or 0.0))
        animate_actor(actor,rig,frame_end)
        create_power_effect(str(actor.get("power_effect") or "none"),rig,frame_end)

    index = int(shot.get("index") or 0)+1
    output = output_dir/f"scene_{index:02d}.mp4"
    stem = output.with_suffix("")
    for stale in output_dir.glob(stem.name + "*.mp4"):
        try:
            stale.unlink()
        except Exception:
            pass

    configure_scene(frame_end,output,powered=powered)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(animation=True)

    # Normalise Blender's actual output to the exact filename expected by Shorts Studio.
    candidates = [
        output,
        stem.with_suffix(".mp4"),
        *sorted(output_dir.glob(stem.name + "*.mp4")),
    ]
    rendered = next(
        (
            path for path in candidates
            if path.exists() and path.is_file() and path.stat().st_size > 4096
        ),
        None,
    )
    if rendered is None:
        files = ", ".join(path.name for path in sorted(output_dir.iterdir()) if path.is_file())
        raise RuntimeError(
            f"Blender finished scene {index} but no MP4 was emitted. "
            f"Expected stem {stem.name}. Files present: {files or 'none'}"
        )
    if rendered.resolve() != output.resolve():
        shutil.move(str(rendered), str(output))

    report = {
        "renderer_version": RENDERER_VERSION,
        "scene": index,
        "duration": duration,
        "frames": frame_end,
        "fps": FPS,
        "output": str(output),
        "bytes": output.stat().st_size,
        "camera": shot.get("camera"),
        "camera_motion": shot.get("camera_motion"),
        "actors": [
            {
                "id": actor.get("id"),
                "clip": actor.get("clip"),
                "power_effect": actor.get("power_effect"),
            }
            for actor in actors
        ],
    }
    (output_dir / f"scene_{index:02d}.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

def main():
    args = parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for shot in plan.get("shots") or []:
        render_shot(shot, output_dir)


if __name__ == "__main__":
    main()
