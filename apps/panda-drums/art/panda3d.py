"""
Panda Drums: the 3D panda, kit and stage, built and rendered with Blender from code.

    python panda3d.py preview out.png [width height samples] [expression] [lens aim]
    python panda3d.py layers outdir [scale samples] [only,these,parts]

`preview` renders the whole scene in one picture. `layers` renders every piece the plugin
animates on its own transparent layer (stage, each drum and cymbal, the body, every face,
the arm parts and the sticks) plus manifest.json with where everything sits on screen.

Needs the `bpy` module (pip install bpy) and the Anton font from ../Resources/fonts.
Units: the panda's head is about 1 unit across its radius; 1 unit is about 10 inches of drum.
"""

import json
import math
import os
import sys

import bpy  # first: it makes bmesh and mathutils importable
import bmesh
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "Resources", "fonts", "Anton-Regular.ttf")

STAGE_W, STAGE_H = 1280, 736

# ---------------------------------------------------------------------------- layout
# The camera is matched to the plugin's stage (1280 x 736): the head lands at about (640, 195)
# with a radius of 119 px, the kick's front head at (640, 588) with a radius of 115 px. The rest
# of the kit is placed by where it should land on the stage (the plugin's slots) and how deep
# it sits, so the rendered parts drop straight into the plugin's layout.
CAMERA = dict(loc=Vector((0.0, -13.4, 4.4)), target=Vector((0.0, 0.6, 3.3)), lens=34.0)

HEAD = Vector((0.0, 1.65, 4.45))
HEAD_R = (1.1, 0.98, 1.0)          # head ellipsoid radii (x, depth, z)
BODY = Vector((0.0, 1.85, 2.75))
PANDA_SCALE = 1.28                 # the panda is built at 1 and scaled about its seat
PANDA_PIVOT = Vector((0.0, 1.9, 1.2))

INCH = 1.18 / 11.0                 # a 22" kick has a radius of 1.18
KICK = dict(pos=Vector((0.0, -0.475, 1.18)), size=22, depth=14)   # front head at y = -1.225
DRUMS = {
    # name: where the top centre lands on the stage, how deep it sits (world y), size and shell
    # depth in inches, tilt towards the camera and to the side (degrees)
    "tom1":  dict(at=(712, 410), y=-0.25, size=10, depth=8, tilt=12, side=-8),
    "tom2":  dict(at=(565, 412), y=-0.2, size=13, depth=10, tilt=12, side=8),
    "tom3":  dict(at=(432, 520), y=-0.75, size=16, depth=16, tilt=6, side=4, floor=True),
    "snare": dict(at=(800, 505), y=-1.0, size=14, depth=5.5, tilt=8, side=-4, snare=True),
}
CYMBALS = {
    # name: where the centre lands, depth, size, tilt towards the camera, side tilt
    "crash1": dict(at=(950, 222), y=0.2, size=18, tilt=22, side=-12),
    "crash2": dict(at=(340, 222), y=0.25, size=19, tilt=22, side=12),
    "ride":   dict(at=(305, 400), y=-0.25, size=21, tilt=18, side=10),
    "splash": dict(at=(815, 150), y=0.6, size=10, tilt=24, side=-6, boom=1.0),
    "china":  dict(at=(210, 262), y=0.6, size=16, tilt=20, side=14, china=True),
}
HIHAT = dict(at=(945, 425), y=-0.55, size=14)

BULB_COLOURS = [(1, 0.08, 0.15), (1, 0.85, 0.15), (0.2, 1, 0.75), (1, 0.3, 0.75)]
BULBS = []                          # (world position, colour) of each heart light, filled by build_stage

EXPRESSIONS = ["neutral", "happy", "open_mouth", "smile", "focused", "excited",
               "wink", "laugh", "surprised", "tongue_out", "angry", "sad"]
WRAPS = ["purple", "brass", "maple", "chrome", "walnut", "black"]    # the plugin's art::Wrap order


def cam_basis():
    c, t = CAMERA["loc"], CAMERA["target"]
    f = (t - c).normalized()
    r = f.cross(Vector((0, 0, 1))).normalized()
    return c, f, r, r.cross(f)


def focal_px():
    return CAMERA["lens"] / 36.0 * STAGE_W


def project(p):
    """World point -> stage pixels (x right, y down)."""
    c, f, r, u = cam_basis()
    d = Vector(p) - c
    z = d.dot(f)
    return (STAGE_W / 2 + focal_px() * d.dot(r) / z, STAGE_H / 2 - focal_px() * d.dot(u) / z)


def at_screen(x, y, world_y):
    """The point on the plane at depth world_y that lands on stage pixel (x, y)."""
    c, f, r, u = cam_basis()
    ray = f + r * ((x - STAGE_W / 2) / focal_px()) + u * ((STAGE_H / 2 - y) / focal_px())
    return c + ray * ((world_y - c.y) / ray.y)


def place(spec):
    return at_screen(spec["at"][0], spec["at"][1], spec["y"])


# ---------------------------------------------------------------------------- scene basics
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.cycles.transparent_max_bounces = 16
    # Keeps the saturated toy colours (AgX washes them out) and still rolls off the highlights.
    sc.view_settings.view_transform = "Khronos PBR Neutral"
    sc.render.resolution_x, sc.render.resolution_y = STAGE_W, STAGE_H
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    return sc


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def mesh_from_bm(name, bm, mat=None, smooth=True, subsurf=0):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = link(bpy.data.objects.new(name, me))
    if mat is not None:
        ob.data.materials.append(mat)
    if subsurf:
        m = ob.modifiers.new("subsurf", "SUBSURF")
        m.levels = m.render_levels = subsurf
    return ob


def sphere(name, loc, scale, mat, seg=48, rings=24, rot=(0, 0, 0), subsurf=1):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    ob = mesh_from_bm(name, bm, mat, subsurf=subsurf)
    ob.location = loc
    ob.scale = scale
    ob.rotation_euler = Euler([math.radians(a) for a in rot])
    return ob


def cylinder(name, loc, r, depth, mat, seg=64, rot=(0, 0, 0), r2=None, cap=True, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    ob = mesh_from_bm(name, bm, mat, smooth=smooth)
    if smooth:
        # Keep the caps flat: auto smooth by angle.
        m = ob.modifiers.new("smooth", "EDGE_SPLIT")
        m.split_angle = math.radians(40)
    ob.location = loc
    ob.rotation_euler = Euler([math.radians(a) for a in rot])
    return ob


def curve(name, points, radius, mat, closed=False, kind="BEZIER", resolution=12):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    cu.resolution_u = resolution
    if kind == "BEZIER":
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(points) - 1)
        for bp, p in zip(sp.bezier_points, points):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = "AUTO"
    else:
        sp = cu.splines.new("POLY")
        sp.points.add(len(points) - 1)
        for pt, p in zip(sp.points, points):
            pt.co = (p[0], p[1], p[2], 1.0)
    sp.use_cyclic_u = closed
    ob = link(bpy.data.objects.new(name, cu))
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def ring(name, centre, r, minor, mat, rot=(0, 0, 0), seg=64):
    pts = [(r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), 0.0) for i in range(seg)]
    ob = curve(name, pts, minor, mat, closed=True, kind="POLY")
    ob.location = centre
    ob.rotation_euler = Euler([math.radians(a) for a in rot])
    return ob


def add_fur(ob, mat_index=0, count=1500, length=0.07, children=24, radius=0.0035, rough=0.02, seed=0, face=False, density=None):
    if face:
        # Short, sparse plush on the face so the eyes, patches and mouth stay crisp; full fluff
        # round the sides and top where it makes the silhouette soft.
        dens = ob.vertex_groups.new(name="fur_density")
        lng = ob.vertex_groups.new(name="fur_length")
        for v in ob.data.vertices:
            front = max(0.0, min(1.0, (-v.co.y - 0.45) / 0.35))
            dens.add([v.index], 1.0 - 0.85 * front, "REPLACE")
            lng.add([v.index], 1.0 - 0.6 * front, "REPLACE")
    if density is not None:
        # Fur only where density(local position) says, e.g. not under the T-shirt.
        dens = ob.vertex_groups.new(name="fur_density")
        for v in ob.data.vertices:
            dens.add([v.index], max(0.0, min(1.0, density(v.co))), "REPLACE")
    mod = ob.modifiers.new("fur", "PARTICLE_SYSTEM")
    ps = mod.particle_system.settings
    mod.particle_system.seed = seed
    ps.type = "HAIR"
    ps.count = count
    ps.hair_length = length
    ps.use_advanced_hair = False      # advanced mode would take the length from emission speed
    ps.child_type = "INTERPOLATED"
    ps.child_percent = 2
    ps.rendered_child_count = children
    ps.render_step = 3
    ps.display_step = 2
    ps.material = mat_index + 1
    ps.root_radius = 1.0
    ps.tip_radius = 0.15
    ps.radius_scale = radius
    ps.roughness_1 = rough
    ps.roughness_2 = rough * 2.0
    ps.roughness_endpoint = rough * 0.5
    ps.child_length = 1.0
    ps.clump_factor = 0.15
    if face or density is not None:
        mod.particle_system.vertex_group_density = "fur_density"
        if face:
            mod.particle_system.vertex_group_length = "fur_length"
    return mod


# ---------------------------------------------------------------------------- materials
def principled(name, color, rough=0.5, metal=0.0, coat=0.0, sheen=0.0, sss=0.0, emission=None, strength=0.0,
               aniso=0.0, transmission=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1.0)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Coat Roughness"].default_value = 0.05
    p.inputs["Sheen Weight"].default_value = sheen
    p.inputs["Sheen Roughness"].default_value = 0.35
    p.inputs["Subsurface Weight"].default_value = sss
    p.inputs["Anisotropic"].default_value = aniso
    p.inputs["Transmission Weight"].default_value = transmission
    p.inputs["Alpha"].default_value = alpha
    if emission is not None:
        p.inputs["Emission Color"].default_value = (*emission, 1.0)
        p.inputs["Emission Strength"].default_value = strength
    return m


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        if k == "op":
            n.operation = v
        elif k == "data_type":
            n.data_type = v
        else:
            n.inputs[k].default_value = v
    return n


def math_node(nt, op, a, b=None, c=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def smoothstep(nt, e0, e1, x):
    t = math_node(nt, "DIVIDE", math_node(nt, "SUBTRACT", x, e0), e1 - e0)
    t = math_node(nt, "MINIMUM", math_node(nt, "MAXIMUM", t, 0.0), 1.0)
    return math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", t, t), math_node(nt, "SUBTRACT", 3.0, math_node(nt, "MULTIPLY", t, 2.0)))


def head_material(white, black):
    """Cream fur with the black eye patches and pink cheeks painted in, in the head's own space,
    so the fur growing out of a patch is black too."""
    m = bpy.data.materials.new("head")
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    for k in ("Roughness", "Sheen Weight", "Sheen Roughness", "Subsurface Weight"):
        p.inputs[k].default_value = white.node_tree.nodes["Principled BSDF"].inputs[k].default_value
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    X = math_node(nt, "ABSOLUTE", sep.outputs[0])
    Y, Z = sep.outputs[1], sep.outputs[2]
    front = smoothstep(nt, -0.25, -0.5, Y)   # 1 on the face, 0 behind

    def ellipse(cx, cz, ax, az, angle):
        dx = math_node(nt, "SUBTRACT", X, cx)
        dz = math_node(nt, "SUBTRACT", Z, cz)
        ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        u = math_node(nt, "ADD", math_node(nt, "MULTIPLY", dx, ca), math_node(nt, "MULTIPLY", dz, sa))
        w = math_node(nt, "SUBTRACT", math_node(nt, "MULTIPLY", dz, ca), math_node(nt, "MULTIPLY", dx, sa))
        d = math_node(nt, "ADD", math_node(nt, "POWER", math_node(nt, "DIVIDE", u, ax), 2.0),
                      math_node(nt, "POWER", math_node(nt, "DIVIDE", w, az), 2.0))
        return d

    patch = math_node(nt, "MULTIPLY", math_node(nt, "SUBTRACT", 1.0, smoothstep(nt, 0.85, 1.0, ellipse(0.43, -0.07, 0.4, 0.31, -32))), front)
    blush = math_node(nt, "MULTIPLY", math_node(nt, "SUBTRACT", 1.0, smoothstep(nt, 0.1, 1.0, ellipse(0.66, -0.38, 0.2, 0.13, 0))), front)

    mix1 = nt.nodes.new("ShaderNodeMix")
    mix1.data_type = "RGBA"
    mix1.inputs[6].default_value = white.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
    mix1.inputs[7].default_value = (1.0, 0.42, 0.55, 1.0)
    nt.links.new(blush, mix1.inputs[0])
    mix2 = nt.nodes.new("ShaderNodeMix")
    mix2.data_type = "RGBA"
    nt.links.new(mix1.outputs[2], mix2.inputs[6])
    mix2.inputs[7].default_value = black.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
    nt.links.new(patch, mix2.inputs[0])
    nt.links.new(mix2.outputs[2], p.inputs["Base Color"])
    # Black fur shines less than white fur.
    sheen = math_node(nt, "SUBTRACT", p.inputs["Sheen Weight"].default_value, math_node(nt, "MULTIPLY", patch, 0.4))
    nt.links.new(sheen, p.inputs["Sheen Weight"])
    return m


def glitter_material():
    """Purple sparkle wrap under a clear coat."""
    m = principled("glitter", (0.06, 0.006, 0.24), rough=0.3, metal=0.3, coat=1.0)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 180.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    # Random flake normals.
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    # Some flakes much brighter.
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.7
    ramp.color_ramp.elements[0].color = (0.06, 0.006, 0.24, 1)
    ramp.color_ramp.elements[1].position = 0.86
    ramp.color_ramp.elements[1].color = (0.55, 0.25, 1.0, 1)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vor.outputs["Color"], sep.inputs[0])
    nt.links.new(sep.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], p.inputs["Base Color"])
    return m


def cymbal_material(color=(1.0, 0.58, 0.13)):
    """Polished brass: lathe grooves in the bump and alternating light and dark tone rings."""
    m = principled("bronze", color, rough=0.2, metal=1.0, aniso=0.6)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    r = math_node(nt, "SQRT", math_node(nt, "ADD", math_node(nt, "POWER", sep.outputs[0], 2.0), math_node(nt, "POWER", sep.outputs[1], 2.0)))
    lathe = math_node(nt, "SINE", math_node(nt, "MULTIPLY", r, 260.0))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(lathe, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    bands = math_node(nt, "MULTIPLY", math_node(nt, "ADD", math_node(nt, "SINE", math_node(nt, "MULTIPLY", r, 22.0)), 1.0), 0.5)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (color[0] * 0.62, color[1] * 0.5, color[2] * 0.35, 1.0)
    mix.inputs[7].default_value = (*color, 1.0)
    nt.links.new(bands, mix.inputs[0])
    nt.links.new(mix.outputs[2], p.inputs["Base Color"])
    tangent = nt.nodes.new("ShaderNodeTangent")
    tangent.direction_type = "RADIAL"
    tangent.axis = "Z"
    nt.links.new(tangent.outputs[0], p.inputs["Tangent"])
    return m


def wood_material(name, light, dark):
    """Clear-coated wood: stretched noise for the grain."""
    m = principled(name, light, rough=0.35, coat=1.0)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2.0, 2.0, 40.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = 3.0
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 4.0
    nt.links.new(mp.outputs[0], wave.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*dark, 1)
    mix.inputs[7].default_value = (*light, 1)
    nt.links.new(wave.outputs["Fac"], mix.inputs[0])
    nt.links.new(mix.outputs[2], p.inputs["Base Color"])
    return m


def iris_material():
    """Dark brown iris, lighter towards the rim, under a glossy coat."""
    m = principled("iris", (0.02, 0.008, 0.004), rough=0.06, coat=1.0)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    r = math_node(nt, "SQRT", math_node(nt, "ADD", math_node(nt, "POWER", sep.outputs[0], 2.0), math_node(nt, "POWER", sep.outputs[2], 2.0)))
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.006, 0.004, 0.003, 1)
    ramp.color_ramp.elements[1].position = 0.92
    ramp.color_ramp.elements[1].color = (0.16, 0.06, 0.02, 1)
    nt.links.new(r, ramp.inputs[0])
    nt.links.new(ramp.outputs[0], p.inputs["Base Color"])
    return m


def dark_in_reflections(m, color=(0.07, 0.035, 0.03)):
    """Seen in a reflection, this surface is a dark warm grey, so metal and gloss pick up the
    studio lights and not the pink of the room (the way a photographer flags a set)."""
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    bsdf = out.inputs["Surface"].links[0].from_socket
    lp = nt.nodes.new("ShaderNodeLightPath")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Glossy Ray"], mix.inputs[0])
    nt.links.new(bsdf, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def image_material(name, path):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.5
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    return m


def make_logo(path, size=1024):
    """The kick's front head: cream with the red CRUSH heart."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    img = Image.new("RGB", (size, size), (246, 241, 232))
    d = ImageDraw.Draw(img)
    # Heart.
    pts = []
    for i in range(400):
        t = 2 * math.pi * i / 400
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((size / 2 + x / 34 * size * 0.78, size * 0.47 + (y + 1.5) / 30 * size * 0.74))
    shadow = Image.new("L", (size, size), 0)
    ImageDraw.Draw(shadow).polygon([(x + 6, y + 10) for x, y in pts], fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img.paste((150, 120, 120), (0, 0), shadow)
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(214, 28, 40))
    d.line(pts + [pts[0]], fill=(40, 10, 14), width=10)
    font = ImageFont.truetype(FONT, int(size * 0.2))
    text = "CRUSH"
    w = d.textlength(text, font=font)
    d.text((size / 2 - w / 2 + 4, size * 0.37 + 6), text, font=font, fill=(110, 10, 20))
    d.text((size / 2 - w / 2, size * 0.37), text, font=font, fill=(250, 246, 238))
    img.save(path)


class Mats:
    def __init__(self, workdir):
        self.white = principled("fur_white", (0.96, 0.9, 0.78), rough=0.7, sheen=0.4, sss=0.12)
        self.black = principled("fur_black", (0.012, 0.011, 0.014), rough=0.55, sheen=0.22)
        self.head = head_material(self.white, self.black)
        self.eye = principled("eye_white", (0.97, 0.97, 0.97), rough=0.18, coat=1.0)
        self.iris = iris_material()
        self.glint = principled("glint", (1, 1, 1), emission=(1, 1, 1), strength=6.0)
        self.plastic = principled("glasses", (0.012, 0.012, 0.014), rough=0.18, coat=1.0)
        self.glass = principled("lens", (1, 1, 1), rough=0.02, transmission=1.0)
        self.nose = principled("nose", (0.02, 0.018, 0.02), rough=0.12, coat=1.0)
        self.mouth = principled("mouth", (0.28, 0.02, 0.04), rough=0.5)
        self.tongue = principled("tongue", (0.92, 0.28, 0.33), rough=0.35, sss=0.2)
        self.shirt = principled("shirt", (0.13, 0.012, 0.52), rough=0.8, sheen=0.12)
        self.shirt_hem = principled("shirt_hem", (0.08, 0.006, 0.36), rough=0.8, sheen=0.12)
        self.heart = principled("heart", (0.8, 0.005, 0.02), rough=0.4)
        self.wood = principled("wood", (0.86, 0.66, 0.42), rough=0.45)
        self.glitter = glitter_material()
        self.chrome = principled("chrome", (0.92, 0.92, 0.94), rough=0.07, metal=1.0)
        self.brass = principled("brass_shell", (0.95, 0.68, 0.3), rough=0.18, metal=1.0, coat=0.5)
        self.maple = wood_material("maple", (0.78, 0.42, 0.14), (0.55, 0.26, 0.07))
        self.walnut = wood_material("walnut", (0.22, 0.1, 0.04), (0.11, 0.045, 0.02))
        self.lacquer = principled("lacquer", (0.012, 0.012, 0.015), rough=0.25, coat=1.0)
        self.felt = principled("felt", (0.35, 0.02, 0.12), rough=0.95, sheen=0.5)
        self.drumhead = principled("drumhead", (0.86, 0.84, 0.78), rough=0.55)
        self.bronze = cymbal_material()
        self.china = cymbal_material((0.8, 0.42, 0.1))
        self.rubber = principled("rubber", (0.02, 0.02, 0.02), rough=0.6)
        self.wall = dark_in_reflections(principled("wall", (0.8, 0.15, 0.36), rough=0.9))
        self.floor = dark_in_reflections(principled("floor", (0.42, 0.06, 0.22), rough=0.55, coat=0.3))
        # No sheen: seen this low it turns the rug pale pink.
        self.rug = dark_in_reflections(principled("rug", (0.2, 0.015, 0.14), rough=0.9))
        self.rug_glow = principled("rug_glow", (1, 0.5, 0.8), emission=(1.0, 0.3, 0.7), strength=6.0)
        # Dark in reflections too, or the cymbals turn green next to them.
        self.bamboo = dark_in_reflections(principled("bamboo", (0.1, 0.42, 0.05), rough=0.35, coat=0.4))
        self.bamboo_node = dark_in_reflections(principled("bamboo_node", (0.05, 0.22, 0.03), rough=0.4))
        self.leaf = dark_in_reflections(principled("leaf", (0.07, 0.38, 0.04), rough=0.5, sss=0.2))
        self.wire = principled("wire", (0.05, 0.05, 0.05), rough=0.4)
        self.bulbs = [principled("bulb%d" % i, tuple(v * 0.4 for v in c), emission=c, strength=0.85)
                      for i, c in enumerate(BULB_COLOURS)]
        logo = os.path.join(workdir, "kick_logo.png")
        make_logo(logo)
        self.logo = image_material("kick_logo", logo)


# ---------------------------------------------------------------------------- the panda
def on_head(x, z, out=0.0):
    """Point on the head's surface (front), x and z relative to the head centre."""
    a, b, c = HEAD_R
    t = max(0.0, 1.0 - (x / a) ** 2 - (z / c) ** 2)
    return HEAD + Vector((x, -b * math.sqrt(t) - out, z))


def decal(name, outline, mat, out=0.004):
    """A flat shape (x, z pairs relative to the head) wrapped onto the face."""
    bm = bmesh.new()
    centre = (sum(p[0] for p in outline) / len(outline), sum(p[1] for p in outline) / len(outline))
    c = bm.verts.new(on_head(*centre, out=out) - HEAD)
    ring_v = [bm.verts.new(on_head(x, z, out=out) - HEAD) for x, z in outline]
    for i in range(len(ring_v)):
        bm.faces.new((c, ring_v[i], ring_v[(i + 1) % len(ring_v)]))
    ob = mesh_from_bm(name, bm, mat)
    ob.location = HEAD
    return ob


def face_curve(name, pts2d, radius, mat, out=0.01):
    return curve(name, [tuple(on_head(x, z, out=out)) for x, z in pts2d], radius, mat)


def arc(cx, cz, rx, rz, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cz + rz * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


def glasses(M, w=0.33, h=0.25, rim=0.058, cx=0.41, cz=0.0, standoff=0.13):
    """One mesh: two rims and the bridge, on a gently curved plane in front of the face."""
    def surface(x, z):
        # A shallow cylinder in front of the face: the frame wraps a little, like real glasses.
        y = on_head(0.0, 0.0).y - standoff + 0.22 * (x / HEAD_R[0]) ** 2
        return Vector((HEAD.x + x, y, HEAD.z + z))

    def rounded_rect(cx, cz, w, h, n=64, p=0.5):
        pts = []
        for i in range(n):
            t = 2 * math.pi * i / n
            ct, st = math.cos(t), math.sin(t)
            pts.append((cx + w * math.copysign(abs(ct) ** p, ct), cz + h * math.copysign(abs(st) ** p, st)))
        return pts

    bm = bmesh.new()
    for side in (-1, 1):
        inner = [bm.verts.new(surface(x, z)) for x, z in rounded_rect(cx * side, cz, w, h)]
        outer = [bm.verts.new(surface(x, z)) for x, z in rounded_rect(cx * side, cz + 0.01, w + rim, h + rim * 0.95)]
        for i in range(len(inner)):
            j = (i + 1) % len(inner)
            bm.faces.new((inner[i], inner[j], outer[j], outer[i]))
    # Bridge: a band joining the two rims a little above centre.
    bx0, bx1 = cx - w - rim * 0.6, -(cx - w - rim * 0.6)
    br = [bm.verts.new(surface(x, z)) for x, z in ((bx0, cz + 0.14), (bx1, cz + 0.14), (bx1, cz + 0.08), (bx0, cz + 0.08))]
    bm.faces.new(br)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ob = mesh_from_bm("glasses", bm, M.plastic, smooth=True)
    sol = ob.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.06
    sol.offset = 0.0
    bev = ob.modifiers.new("round", "BEVEL")
    bev.width = 0.018
    bev.segments = 3
    bev.limit_method = "ANGLE"
    ws = ob.modifiers.new("ws", "WEIGHTED_NORMAL")
    for side in (-1, 1):
        hinge = surface((cx + w + rim * 0.8) * side, cz + 0.12)
        temple = curve("temple%d" % side, [tuple(hinge), tuple(HEAD + Vector((1.04 * side, -0.35, 0.14))), tuple(HEAD + Vector((1.1 * side, 0.15, 0.18)))], 0.035, M.plastic)
        temple.parent = ob
    return ob


def build_face(M, expr, objects):
    """Eyes, glasses, nose, mouth and brows for one expression."""
    add = objects.append
    eyes = {"neutral": "open", "happy": "open", "open_mouth": "open", "smile": "soft", "focused": "focused",
            "excited": "wide", "wink": "wink", "laugh": "closed", "surprised": "wide", "tongue_out": "open",
            "angry": "angry", "sad": "sad", "blink": "shut"}[expr]
    mouth = {"neutral": "grin", "happy": "open", "open_mouth": "wide", "smile": "grin", "focused": "flat",
             "excited": "wide", "wink": "open", "laugh": "wide", "surprised": "o", "tongue_out": "tongue",
             "angry": "frown", "sad": "sad", "blink": "grin"}[expr]

    for side in (-1, 1):
        ex, ez = 0.41 * side, 0.0
        centre = on_head(ex, ez, out=-0.075)
        closed = eyes == "closed" or (eyes == "wink" and side == 1)
        if closed:
            # Laughing eye: a ^ arc on the patch.
            pts = arc(ex, ez - 0.07, 0.15, 0.11, 25, 155)
            add(face_curve("lash%d" % side, pts, 0.024, M.eye, out=0.02))
            continue
        if eyes == "shut":
            # Blink: lids down, a soft lash line.
            pts = arc(ex, ez + 0.06, 0.15, 0.07, 205, 335)
            add(face_curve("lash%d" % side, pts, 0.02, M.eye, out=0.02))
            continue
        scale = 1.12 if eyes == "wide" else 1.0
        add(sphere("eye%d" % side, centre, (0.175 * scale, 0.14, 0.19 * scale), M.eye))
        pupil = 0.78 if eyes == "wide" else 1.0
        look = Vector((-0.015 * side, 0, -0.01))
        add(sphere("iris%d" % side, centre + Vector((0, -0.088, -0.005)) + look, (0.15 * pupil, 0.075, 0.162 * pupil), M.iris))
        add(sphere("glint%d" % side, centre + Vector((-0.05, -0.165, 0.065)) + look, (0.045, 0.016, 0.045), M.glint, seg=16, rings=8))
        add(sphere("glint2%d" % side, centre + Vector((0.05, -0.16, -0.055)) + look, (0.02, 0.01, 0.02), M.glint, seg=12, rings=6))
        lid = {"focused": 52, "angry": 48, "sad": 40, "soft": 22}.get(eyes, 0)
        if lid:
            # Upper lid: black cap that slides down over the eye.
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=1.0)
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0),
                                   plane_no=(0, 0, 1), clear_inner=True)
            ob = mesh_from_bm("lid%d" % side, bm, M.black)
            ob.location = centre
            ob.scale = (0.2 * scale, 0.175, 0.215 * scale)
            slant = {"angry": -22 * side, "sad": 18 * side}.get(eyes, 0)
            # Tipping the cap forward by `lid` degrees brings it down over the front of the eye.
            ob.rotation_euler = Euler((math.radians(lid), math.radians(slant), 0))
            add(ob)

    # Glasses: flat moulded plastic fronts (rounded rectangles), a keyhole bridge, arms to the ears.
    add(glasses(M))

    # Nose.
    add(sphere("nose", on_head(0.0, -0.2, out=0.05), (0.12, 0.08, 0.085), M.nose, rot=(-10, 0, 0)))
    add(sphere("noseglint", on_head(-0.035, -0.17, out=0.13), (0.03, 0.01, 0.015), M.glint, seg=12, rings=6))

    # Mouth.
    mz = -0.38
    if mouth in ("open", "wide", "tongue"):
        w = {"open": 0.25, "wide": 0.31, "tongue": 0.24}[mouth]
        h = {"open": 0.21, "wide": 0.28, "tongue": 0.18}[mouth]
        top = [(-w + 2 * w * i / 15, mz + 0.02 - 0.03 * math.sin(math.pi * i / 15)) for i in range(16)]
        bottom = [(w * math.cos(math.radians(a)), mz + 0.02 - h * math.sin(math.radians(a))) for a in range(5, 180, 8)]
        outline = top + bottom[::-1][1:]
        add(decal("mouth", outline, M.mouth, out=0.03))
        tw = w * 0.62
        tongue = [(tw * math.cos(math.radians(a)), mz + 0.02 - h * 0.98 + h * 0.5 * math.sin(math.radians(a)) + 0.01)
                  for a in range(0, 361, 15)]
        if mouth == "tongue":
            tongue = [(0.11 * math.cos(math.radians(a)), mz - h - 0.02 + 0.12 * math.sin(math.radians(a))) for a in range(0, 361, 15)]
            add(decal("tongue", tongue, M.tongue, out=0.05))
        else:
            add(decal("tongue", tongue, M.tongue, out=0.035))
        add(face_curve("lip", outline + [outline[0]], 0.018, M.nose, out=0.034))
    elif mouth == "o":
        o = [(0.085 * math.cos(math.radians(a)), mz - 0.08 + 0.1 * math.sin(math.radians(a))) for a in range(0, 360, 12)]
        add(decal("mouth", o, M.mouth, out=0.03))
        add(face_curve("lip", o + [o[0]], 0.018, M.nose, out=0.034))
    else:
        curve_pts = {"grin": arc(0.0, mz + 0.08, 0.17, 0.11, 200, 340),
                     "flat": [(-0.1, mz - 0.02), (0.0, mz - 0.03), (0.1, mz - 0.02)],
                     "frown": arc(0.0, mz - 0.1, 0.13, 0.07, 20, 160),
                     "sad": arc(0.0, mz - 0.12, 0.11, 0.06, 25, 155)}[mouth]
        add(face_curve("mouthline", curve_pts, 0.022, M.nose, out=0.03))
    # Philtrum.
    add(face_curve("philtrum", [(0.0, -0.27), (0.0, mz + 0.03)], 0.016, M.nose, out=0.03))

    # Brows: only when the face needs them.
    brow = {"angry": (-14, 0.38), "sad": (16, 0.42), "surprised": (0, 0.52), "focused": (-6, 0.4)}.get(expr)
    if brow:
        angle, z = brow
        for side in (-1, 1):
            a = math.radians(angle) * side
            x0, x1 = 0.24 * side, 0.52 * side
            z0, z1 = z + math.tan(-a) * 0.14, z - math.tan(-a) * 0.14
            add(face_curve("brow%d" % side, [(x0, z0), ((x0 + x1) / 2, (z0 + z1) / 2 + 0.03), (x1, z1)], 0.032, M.black, out=0.03))


EAR = Vector((0.8, 0.22, 0.8))      # ear centre from the head centre (x mirrored)


def build_head(M, expr, ears=True):
    objs = []
    head = sphere("head", HEAD, HEAD_R, M.head, seg=96, rings=48)
    head.data.materials.append(M.head)
    add_fur(head, count=6500, length=0.1, children=24, radius=0.0028, seed=1, face=True)
    objs.append(head)
    if ears:
        for side in (-1, 1):
            objs.append(build_ear(M, side))
    build_face(M, expr, objs)
    return objs


def build_ear(M, side):
    ear = sphere("ear%d" % side, HEAD + Vector((EAR.x * side, EAR.y, EAR.z)), (0.38, 0.24, 0.37), M.black, rot=(0, 25 * side, 0))
    add_fur(ear, count=900, length=0.06, children=20, radius=0.003, seed=2 + side)
    return ear


def ear_pivot(side):
    """Where an ear joins the head: it wiggles about this point."""
    return HEAD + Vector((EAR.x * side * 0.72, EAR.y, EAR.z * 0.72))


def build_sleeve(M, side):
    sl = cylinder("sleeve%d" % side, BODY + Vector((1.12 * side, -0.05, 0.62)), 0.34, 0.55, M.shirt, rot=(0, 62 * side, 0), r2=0.39)
    s = sl.modifiers.new("sub", "SUBSURF")
    s.levels = s.render_levels = 2
    return sl


SLEEVE_LEN = 0.62


def build_sleeve_part(M, side):
    """The sleeve on its own for the plugin: hanging straight down from the shoulder (a rounded
    top, flaring a little to a hemmed opening), so it can be turned with the upper arm."""
    top = shoulder(side)
    objs = []
    # Open at the cuff, so the inside shows dark round the arm.
    tube = cylinder("sleeve_tube%d" % side, top - Vector((0, 0, SLEEVE_LEN / 2)), 0.34, SLEEVE_LEN, M.shirt, r2=0.29, cap=False)
    sol = tube.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.03
    objs.append(tube)
    objs.append(sphere("sleeve_cap%d" % side, top, (0.29, 0.29, 0.18), M.shirt))
    objs.append(ring("sleeve_hem%d" % side, top - Vector((0, 0, SLEEVE_LEN - 0.02)), 0.345, 0.03, M.shirt_hem))
    return objs


def build_body(M, sleeves=True):
    objs = []
    torso = sphere("torso", BODY, (1.2, 0.98, 1.12), M.white)
    add_fur(torso, count=2500, length=0.06, children=20, seed=4, density=lambda co: (-0.2 - co.z) / 0.08)
    objs.append(torso)
    # T-shirt: a shell over the upper body, open at the bottom.
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, -0.38), plane_no=(0, 0, -1), clear_outer=True)
    shirt = mesh_from_bm("shirt", bm, M.shirt, subsurf=1)
    shirt.location = BODY + Vector((0, 0, 0.1))
    shirt.scale = (1.25, 1.03, 1.12)
    sol = shirt.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.04
    objs.append(shirt)
    for side in (-1, 1):
        if sleeves:
            objs.append(build_sleeve(M, side))
        leg = sphere("leg%d" % side, BODY + Vector((0.78 * side, -0.85, -1.35)), (0.45, 0.55, 0.42), M.black)
        add_fur(leg, count=800, length=0.06, children=16, seed=6 + side)
        objs.append(leg)
    # The heart on the chest (the panda's left).
    pts = []
    for i in range(40):
        t = 2 * math.pi * i / 40
        x = 16 * math.sin(t) ** 3 / 16 * 0.14
        z = (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) / 16 * 0.13
        pts.append((x, z))
    c = BODY + Vector((0.5, -1.04, 0.55))
    bm = bmesh.new()
    cv = bm.verts.new((0, 0, 0))
    rv = [bm.verts.new((x, 0, z)) for x, z in pts]
    for i in range(len(rv)):
        bm.faces.new((cv, rv[i], rv[(i + 1) % len(rv)]))
    heart = mesh_from_bm("chestheart", bm, M.heart)
    heart.location = c
    heart.rotation_euler = Euler((0, 0, math.radians(-12)))
    sol = heart.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.02
    objs.append(heart)
    return objs


def shoulder(side):
    return BODY + Vector((1.25 * side, -0.25, 0.48))


ARM_R = 0.2                         # arm radius
STICK = dict(back=0.28, length=2.3)  # how far the butt sticks out behind the paw; full length


def fur_tube(M, name, points, radius, fur=1400, seed=10):
    """A furry black tube along points (converted to a mesh so fur can grow on it)."""
    tube_curve = curve(name, [tuple(p) for p in points], radius, M.black)
    tube_curve.data.bevel_resolution = 8
    mesh = bpy.data.meshes.new_from_object(tube_curve.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tube_curve)
    ob = link(bpy.data.objects.new(name, mesh))
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.append(M.black)
    add_fur(ob, count=fur, length=0.055, children=18, seed=seed)
    return ob


def build_paw(M, name, centre, direction, seed=12):
    """A round paw gripping a stick that runs along `direction`, thumb over the top."""
    objs = []
    pw = sphere(name, centre, (0.24, 0.22, 0.22), M.black)
    add_fur(pw, count=500, length=0.045, children=14, seed=seed)
    objs.append(pw)
    up = Vector((0, 0, 1)) - direction * direction.z
    up.normalize()
    th = sphere(name + "_thumb", centre + direction * 0.1 + up * 0.15 + Vector((0, -0.08, 0)), (0.11, 0.1, 0.085), M.black)
    add_fur(th, count=150, length=0.04, children=12, seed=seed + 1)
    objs.append(th)
    for k in range(3):
        pad = sphere(name + "_knuckle%d" % k, centre + direction * (0.12 - 0.09 * k) + Vector((0, -0.17, -0.06)), (0.07, 0.05, 0.07), M.black, seg=16, rings=8)
        objs.append(pad)
    return objs


def build_stick(M, name, butt, tip):
    direction = (tip - butt).normalized()
    length = (tip - butt).length
    st = cylinder(name, (butt + tip) * 0.5, 0.042, length, M.wood, seg=24, r2=0.028)
    st.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    bead = sphere(name + "_bead", tip, (0.042, 0.042, 0.06), M.wood, seg=16, rings=8)
    bead.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return [st, bead]


def build_arm(M, side, paw, stick_tip, name="arm"):
    """A plush arm from the sleeve to the paw, holding a stick that points at stick_tip."""
    s = shoulder(side)
    d = (paw - s)
    elbow = s + d * 0.5 + Vector((0.25 * side, -0.25, -0.35)) * min(1.0, 2.2 / max(0.5, d.length))
    objs = [fur_tube(M, "%s%d" % (name, side), [s, elbow, paw], ARM_R, seed=10 + side)]
    direction = (stick_tip - paw).normalized()
    objs += build_paw(M, "paw%d" % side, paw, direction, seed=12 + side)
    objs += build_stick(M, "stick%d" % side, paw - direction * STICK["back"], stick_tip)
    return objs


# ---------------------------------------------------------------------------- the kit
def lathe(name, profile, mat, seg=96, thickness=0.0, subsurf=1):
    """Spin (radius, height) points round the z axis."""
    bm = bmesh.new()
    rings = [[bm.verts.new((r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg), z)) for r, z in profile]
             for k in range(seg)]
    for k in range(seg):
        a, b = rings[k], rings[(k + 1) % seg]
        for i in range(len(profile) - 1):
            bm.faces.new((a[i], b[i], b[i + 1], a[i + 1]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ob = mesh_from_bm(name, bm, mat, subsurf=subsurf)
    if thickness:
        sol = ob.modifiers.new("thick", "SOLIDIFY")
        sol.thickness = thickness
        ob.modifiers.move(len(ob.modifiers) - 1, 0)
    return ob


def tube(name, a, b, r, mat):
    return curve(name, [tuple(a), tuple(b)], r, mat, kind="POLY")


def tripod(M, base, spread=0.55, name="tripod", hub=0.62):
    """Three legs with braces, the way real hardware stands: hub collar, brace collar, rubber feet."""
    objs = []
    hub_p = Vector((base.x, base.y, hub))
    brace_p = Vector((base.x, base.y, hub * 0.5))
    objs.append(cylinder(name + "_hub", hub_p, 0.07, 0.09, M.chrome, seg=24))
    objs.append(cylinder(name + "_collar", brace_p, 0.06, 0.06, M.chrome, seg=24))
    for k in range(3):
        a = math.radians(90 + 120 * k)
        foot = Vector((base.x + spread * math.cos(a), base.y + spread * math.sin(a), 0.03))
        objs.append(tube(name + "_leg%d" % k, hub_p, foot, 0.028, M.chrome))
        objs.append(tube(name + "_brace%d" % k, brace_p, hub_p.lerp(foot, 0.55), 0.016, M.chrome))
        objs.append(sphere(name + "_foot%d" % k, foot, (0.055, 0.055, 0.035), M.rubber, seg=12, rings=6))
    return objs


def stand(M, top, spread=0.55, boom=None, name="stand"):
    """A cymbal stand up to `top`: tripod, two-section pole with a clutch, optional boom arm,
    and the tilter with felts and a wing nut under and over the cymbal."""
    objs = []
    if boom:
        # The pole stands off to the side (away from the middle) and a boom reaches over.
        out = 1.0 if top.x >= 0 else -1.0
        pole_top = Vector((top.x + out * boom, top.y + 0.25, top.z - 0.75))
    else:
        pole_top = top - Vector((0, 0, 0.12))
    base = Vector((pole_top.x, pole_top.y, 0.0))
    objs += tripod(M, base, spread, name + "_tripod")
    split = 0.62 + (pole_top.z - 0.62) * 0.55
    objs.append(tube(name + "_pole", (base.x, base.y, 0.62), (base.x, base.y, split), 0.04, M.chrome))
    objs.append(tube(name + "_inner", (base.x, base.y, split), pole_top, 0.028, M.chrome))
    objs.append(cylinder(name + "_clutch", (base.x, base.y, split), 0.058, 0.08, M.chrome, seg=24))
    objs.append(sphere(name + "_wing", Vector((base.x + 0.07, base.y - 0.03, split)), (0.05, 0.015, 0.035), M.chrome, seg=12, rings=6))
    if boom:
        objs.append(cylinder(name + "_joint", pole_top, 0.06, 0.08, M.chrome, seg=24))
        objs.append(tube(name + "_boom", pole_top, top - Vector((0, 0, 0.1)), 0.026, M.chrome))
        objs.append(sphere(name + "_weight", pole_top + (pole_top - top).normalized() * 0.35, (0.07, 0.07, 0.07), M.chrome, seg=16, rings=8))
    else:
        objs.append(tube(name + "_tilt", pole_top, top - Vector((0, 0, 0.06)), 0.024, M.chrome))
    objs.append(cylinder(name + "_felt", top - Vector((0, 0, 0.045)), 0.06, 0.03, M.felt, seg=20))
    objs.append(cylinder(name + "_nut", top + Vector((0, 0, 0.13)), 0.035, 0.05, M.chrome, seg=6))
    objs.append(sphere(name + "_nutwing", top + Vector((0, 0, 0.13)), (0.08, 0.012, 0.03), M.chrome, seg=12, rings=6))
    return objs


def cymbal_disc(M, name, centre, r, tilt, side, kind="crash", flip=False):
    """A spun cymbal: bell and bow (a china turns its edge up), tipped towards the camera."""
    if kind == "china":
        prof = [(0.0, 0.09), (0.1, 0.088), (0.14, 0.07), (0.16, 0.035), (0.4, 0.022), (0.72, 0.004), (0.84, 0.0), (0.92, 0.012), (1.0, 0.04)]
    else:
        bell = 0.22 if kind != "ride" else 0.25
        prof = [(0.0, 0.11), (0.08, 0.107), (bell * 0.7, 0.092), (bell * 0.9, 0.065), (bell, 0.045), (0.4, 0.03), (0.7, 0.014), (0.95, 0.002), (1.0, 0.0)]
    mat = M.china if kind == "china" else M.bronze
    ob = lathe(name, [(pr * r, pz * r * (0.85 if kind == "ride" else 1.0)) for pr, pz in prof], mat, seg=128, thickness=0.012)
    rot = Euler((math.radians(tilt), math.radians(side), 0)).to_matrix().to_4x4()
    ob.matrix_world = Matrix.Translation(centre) @ rot @ (Matrix.Diagonal((1, 1, -1, 1)) if flip else Matrix.Identity(4))
    return ob


def wrap_material(M, wrap):
    return {"purple": M.glitter, "brass": M.brass, "maple": M.maple, "chrome": M.chrome,
            "walnut": M.walnut, "black": M.lacquer}[wrap]


def drum(M, name, spec, pos=None, wrap="purple", mount=True):
    objs = []
    pos = pos if pos is not None else place(spec)
    r, depth = spec["size"] * INCH / 2, spec["depth"] * INCH
    rot = Euler((math.radians(spec["tilt"]), math.radians(spec.get("side", 0)), 0))
    mat = Matrix.Translation(pos) @ rot.to_matrix().to_4x4()
    shell = cylinder(name + "_shell", (0, 0, 0), r, depth, wrap_material(M, wrap))
    shell.matrix_world = mat @ Matrix.Translation((0, 0, -depth / 2))
    objs.append(shell)
    head = cylinder(name + "_head", (0, 0, 0), r * 0.985, 0.012, M.drumhead)
    head.matrix_world = mat @ Matrix.Translation((0, 0, 0.004))
    objs.append(head)
    for z in (0.0, -depth):
        hoop = ring(name + "_hoop", (0, 0, 0), r + 0.015, 0.03, M.chrome)
        hoop.matrix_world = mat @ Matrix.Translation((0, 0, z))
        objs.append(hoop)
    n = max(6, int(r * 12)) // 2 * 2
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        lug = sphere(name + "_lug", (0, 0, 0), (1, 1, 1), M.chrome, seg=16, rings=8, subsurf=0)
        lug.matrix_world = mat @ Matrix.Translation((math.cos(a) * (r + 0.035), math.sin(a) * (r + 0.035), -depth / 2)) @ Matrix.Diagonal((0.04, 0.04, min(0.11, depth * 0.3), 1))
        objs.append(lug)
        for z in (0.0, -depth):
            rod = cylinder(name + "_rod", (0, 0, 0), 0.012, min(0.12, depth * 0.4), M.chrome, seg=8)
            inward = min(0.06, depth * 0.2) * (-1 if z == 0.0 else 1)
            rod.matrix_world = mat @ Matrix.Translation((math.cos(a) * (r + 0.035), math.sin(a) * (r + 0.035), z + inward))
            objs.append(rod)
    if spec.get("floor"):
        for k in range(3):
            a = math.radians(-60 + 120 * k + (180 if pos.x > 0 else 0))
            p0 = mat @ Vector((math.cos(a) * (r + 0.07), math.sin(a) * (r + 0.07), -depth * 0.3))
            objs.append(cylinder(name + "_bracket", p0, 0.045, 0.1, M.chrome, seg=12))
            foot = Vector((p0.x + math.cos(a) * 0.18, p0.y + math.sin(a) * 0.18, 0.03))
            objs.append(tube(name + "_leg", p0, foot, 0.028, M.chrome))
            objs.append(sphere(name + "_foot", foot, (0.05, 0.05, 0.035), M.rubber, seg=12, rings=6))
    elif spec.get("snare"):
        basket = pos - Vector((0, 0, depth + 0.08))
        objs += tripod(M, Vector((basket.x, basket.y, 0)), 0.5, name + "_tripod", hub=min(0.62, basket.z * 0.45))
        objs.append(tube(name + "_pole", (basket.x, basket.y, 0.4), basket, 0.035, M.chrome))
        for k in range(3):
            a = math.radians(90 + 120 * k)
            tip = mat @ Vector((math.cos(a) * r * 0.75, math.sin(a) * r * 0.75, -depth - 0.04))
            objs.append(tube(name + "_arm%d" % k, basket, tip, 0.02, M.chrome))
        objs.append(cylinder(name + "_throw", mat @ Vector((r + 0.06, 0, -depth * 0.5)), 0.03, depth * 0.6, M.chrome, seg=12))
    elif mount:
        p0 = mat @ Vector((0, 0, -depth))
        kick_top = KICK["pos"] + Vector((0.18 * math.copysign(1, pos.x), 0.25, KICK["size"] * INCH / 2 * 0.92))
        objs.append(tube(name + "_mount", p0, kick_top, 0.04, M.chrome))
        objs.append(cylinder(name + "_clamp", p0, 0.06, 0.1, M.chrome, seg=16))
    return objs


def kick(M, wrap="purple"):
    objs = []
    k = KICK
    centre, r, depth = k["pos"], k["size"] * INCH / 2, k["depth"] * INCH
    shell = cylinder("kick_shell", centre, r, depth, wrap_material(M, wrap), rot=(90, 0, 0))
    objs.append(shell)
    front_y = centre.y - depth / 2
    front = cylinder("kick_front", (centre.x, front_y - 0.006, centre.z), r * 0.975, 0.01, M.logo, rot=(90, 0, 0), smooth=False)
    # Map the logo straight onto the front head.
    me = front.data
    uv = me.uv_layers.new()
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (0.5 + v.x / (2 * r * 0.975), 0.5 + v.y / (2 * r * 0.975))
    objs.append(front)
    for y in (front_y, centre.y + depth / 2):
        objs.append(ring("kick_hoop", (centre.x, y, centre.z), r + 0.03, 0.065, wrap_material(M, wrap), rot=(90, 0, 0)))
        objs.append(ring("kick_hoop_edge", (centre.x, y - 0.03, centre.z), r + 0.0, 0.02, M.chrome, rot=(90, 0, 0)))
    for i in range(10):
        a = 2 * math.pi * (i + 0.5) / 10
        objs.append(sphere("kick_claw", (centre.x + math.cos(a) * (r + 0.05), front_y + 0.12, centre.z + math.sin(a) * (r + 0.05)), (0.05, 0.12, 0.05), M.chrome, seg=12, rings=6, subsurf=0))
        objs.append(sphere("kick_lug", (centre.x + math.cos(a) * (r + 0.035), centre.y, centre.z + math.sin(a) * (r + 0.035)), (0.045, 0.14, 0.045), M.chrome, seg=12, rings=6, subsurf=0))
    for side in (-1, 1):
        objs.append(tube("kick_spur", (centre.x + side * r * 0.8, front_y + 0.3, centre.z - r * 0.45), (centre.x + side * r * 1.2, front_y + 0.05, 0.03), 0.035, M.chrome))
    return objs


def hihat(M, pos=None):
    objs = []
    c = pos if pos is not None else place(HIHAT)
    r = HIHAT["size"] * INCH / 2
    objs.append(cymbal_disc(M, "hat_top", c + Vector((0, 0, 0.05)), r, 16, -4))
    objs.append(cymbal_disc(M, "hat_bottom", c - Vector((0, 0, 0.03)), r, 16, -4, flip=True))
    objs += tripod(M, Vector((c.x, c.y, 0.0)), 0.5, "hat_tripod")
    objs.append(tube("hat_pole", (c.x, c.y, 0.62), c - Vector((0, 0, 0.08)), 0.04, M.chrome))
    objs.append(tube("hat_rod", c - Vector((0, 0, 0.08)), c + Vector((0, 0, 0.32)), 0.016, M.chrome))
    objs.append(cylinder("hat_clutch", c + Vector((0, 0, 0.14)), 0.05, 0.08, M.chrome, seg=16))
    # Pedal: chrome frame with a black footboard, hinged at the heel.
    heel = Vector((c.x - 0.1, c.y - 0.75, 0.04))
    toe = Vector((c.x - 0.1, c.y - 0.1, 0.2))
    objs.append(tube("hat_frame_l", heel + Vector((-0.12, 0, 0)), Vector((c.x - 0.22, c.y, 0.03)), 0.018, M.chrome))
    objs.append(tube("hat_frame_r", heel + Vector((0.12, 0, 0)), Vector((c.x + 0.02, c.y, 0.03)), 0.018, M.chrome))
    board = cylinder("hat_board", (heel + toe) / 2, 0.15, (toe - heel).length, M.lacquer, seg=4, rot=(90 - math.degrees(math.atan2(toe.z - heel.z, toe.y - heel.y)), 0, 45))
    board.scale = (1.0, 0.25, 1.0)
    objs.append(board)
    objs.append(tube("hat_chain", toe, Vector((c.x, c.y, 0.55)), 0.012, M.chrome))
    return objs


def build_kit(M, mounts=True):
    parts = {"kick": kick(M), "hihat": hihat(M)}
    for name, spec in DRUMS.items():
        parts[name] = drum(M, name, spec, mount=mounts)
    for name, spec in CYMBALS.items():
        c = place(spec)
        kind = "china" if spec.get("china") else "ride" if name == "ride" else "crash"
        parts[name] = [cymbal_disc(M, name, c, spec["size"] * INCH / 2, spec["tilt"], spec["side"], kind)]
        parts[name] += stand(M, c, boom=spec.get("boom"), name=name + "_stand")
    return parts


# ---------------------------------------------------------------------------- the stage
def build_stage(M):
    objs = []
    BULBS.clear()
    wall = cylinder("wall", (0, 7.0, 6), 30, 0.2, M.wall, rot=(90, 0, 0), seg=8, smooth=False)
    objs.append(wall)
    floor = cylinder("floor", (0, 0, -0.1), 30, 0.2, M.floor, seg=8, smooth=False)
    objs.append(floor)
    rug = cylinder("rug", (0, 0.4, 0.02), 4.6, 0.04, M.rug, seg=128)
    rug.scale = (1.15, 0.7, 1)
    objs.append(rug)
    glow = ring("rug_ring", (0, 0.4, 0.045), 4.35, 0.035, M.rug_glow)
    glow.scale = (1.15, 0.7, 1)
    objs.append(glow)
    # Bamboo at both sides.
    for x, y, h, n in ((-5.9, 3.5, 9, 5), (-5.1, 4.6, 8, 4), (5.9, 3.5, 9, 5), (5.2, 4.6, 8, 4)):
        for k in range(n):
            seg_len = h / n
            z0 = k * seg_len
            objs.append(cylinder("bamboo", (x, y, z0 + seg_len / 2), 0.17, seg_len - 0.04, M.bamboo, seg=24))
            objs.append(cylinder("bamboo_node", (x, y, z0 + seg_len), 0.19, 0.06, M.bamboo_node, seg=24))
            for j in range(2):
                a = (k * 2 + j) * 1.7 + x
                leaf = sphere("leaf", (x + math.cos(a) * 0.55, y + math.sin(a) * 0.3, z0 + seg_len * (0.6 + 0.3 * j)), (0.55, 0.12, 0.025), M.leaf, seg=24, rings=8)
                leaf.rotation_euler = Euler((math.radians(10), math.radians(-25 * math.copysign(1, math.cos(a))), a))
                objs.append(leaf)
    # Heart lights on a wire across the back.
    wire_pts = []
    for i in range(41):
        t = i / 40
        x = -7.5 + 15 * t
        z = 8.6 - 1.2 * (1 - (2 * t - 1) ** 2)
        wire_pts.append((x, 5.2, z))
    objs.append(curve("wire", wire_pts, 0.02, M.wire, kind="POLY"))
    for i in range(16):
        t = (i + 0.5) / 16
        x = -7.5 + 15 * t
        z = 8.6 - 1.2 * (1 - (2 * t - 1) ** 2) - 0.25
        pts = []
        for k in range(32):
            a = 2 * math.pi * k / 32
            hx = 16 * math.sin(a) ** 3 / 16 * 0.26
            hz = (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16 * 0.25
            pts.append((hx, hz))
        bm = bmesh.new()
        cv = bm.verts.new((0, 0, 0))
        rv = [bm.verts.new((hx, 0, hz)) for hx, hz in pts]
        for k in range(len(rv)):
            bm.faces.new((cv, rv[k], rv[(k + 1) % len(rv)]))
        h = mesh_from_bm("bulb", bm, M.bulbs[i % 4])
        h.location = (x, 5.15, z)
        BULBS.append((Vector((x, 5.15, z)), BULB_COLOURS[i % 4]))
        s = h.modifiers.new("thick", "SOLIDIFY")
        s.thickness = 0.08
        objs.append(h)
        # Each bulb throws a little pool of its colour on the wall.
        glow = bpy.data.lights.new("bulb_glow", "POINT")
        glow.energy = 18.0
        glow.shadow_soft_size = 0.15
        glow.color = M.bulbs[i % 4].node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value[:3]
        lo = link(bpy.data.objects.new("bulb_glow", glow))
        lo.location = (x, 5.0, z - 0.05)
        objs.append(lo)
    return objs


def lights_and_camera(sc):
    def area(name, loc, target, energy, size, color=(1, 1, 1)):
        l = bpy.data.lights.new(name, "AREA")
        l.energy = energy
        l.size = size
        l.color = color
        ob = link(bpy.data.objects.new(name, l))
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        return ob
    area("key", (-5.5, -9, 10.5), (0, 0.5, 3.2), 3200, 6, (1.0, 0.96, 0.92))
    area("fill", (7, -8, 5), (0, 0.5, 3), 1300, 7, (1.0, 0.86, 0.94))
    area("rim", (0.5, 7.5, 9), (0, 1.5, 4), 2200, 5, (1.0, 0.85, 0.95))
    area("top", (0, -2, 12), (0, 0, 2), 900, 8)
    # A warm soft box above and behind the kit that only metal and gloss can see: it is what
    # the cymbals and chrome reflect, as in a product shot.
    for name, loc, size, energy in (("bounce_top", (0, 4.0, 11.5), (16, 5), 9.0), ("bounce_back", (0, 6.5, 7.5), (16, 3), 5.0),
                                    ("bounce_front", (-3.0, -11.0, 9.5), (5, 2.5), 1.6)):
        bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
        card = bpy.context.active_object
        card.name = name
        card.scale = (size[0], size[1], 1)
        card.rotation_euler = (Vector((0, -2, 3)) - Vector(loc)).to_track_quat("Z", "Y").to_euler()
        card.data.materials.append(principled(name, (0, 0, 0), emission=(1.0, 0.86, 0.62), strength=energy))
        card.visible_camera = card.visible_diffuse = card.visible_shadow = False
        card.visible_transmission = card.visible_volume_scatter = False
    world = bpy.data.worlds.new("world")
    sc.world = world
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (1.0, 0.5, 0.7, 1)
    bg.inputs["Strength"].default_value = 0.25
    cam = bpy.data.cameras.new("cam")
    cam.lens = CAMERA["lens"]
    co = link(bpy.data.objects.new("cam", cam))
    co.location = CAMERA["loc"]
    co.rotation_euler = (CAMERA["target"] - CAMERA["loc"]).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    return co


def to_panda_space(world):
    """Where a world point is before the panda is scaled up about its seat."""
    return PANDA_PIVOT + (world - PANDA_PIVOT) / PANDA_SCALE


def scale_panda(objs):
    pivot = bpy.data.objects.new("panda", None)
    link(pivot)
    pivot.location = PANDA_PIVOT
    for ob in objs:
        ob.parent = pivot
        ob.matrix_parent_inverse = Matrix.Translation(-PANDA_PIVOT)
    pivot.scale = (PANDA_SCALE,) * 3
    bpy.context.view_layer.update()
    return pivot


def default_arms(M):
    """The preview pose: one stick up, one on the snare."""
    objs = []
    objs += build_arm(M, -1, shoulder(-1) + Vector((-0.4, -0.75, 0.85)), shoulder(-1) + Vector((-0.2, -0.95, 2.0)))
    snare = to_panda_space(place(DRUMS["snare"]) + Vector((-0.1, 0.0, 0.05)))
    paw = snare + Vector((-0.45, 0.25, 0.6))
    objs += build_arm(M, 1, paw, snare)
    return objs


# ---------------------------------------------------------------------------- entry points
def preview(out, width=STAGE_W, height=STAGE_H, samples=64, expr="happy", lens=None, aim=None):
    """The whole scene in one picture. lens and aim (the height the camera looks at) widen the
    shot for posters: the parts the plugin uses always render with the stage camera."""
    sc = reset()
    workdir = os.path.dirname(os.path.abspath(out))
    M = Mats(workdir)
    build_stage(M)
    build_kit(M)
    scale_panda(build_body(M) + build_head(M, expr) + default_arms(M))
    cam = lights_and_camera(sc)
    if lens:
        cam.data.lens = lens
    if aim:
        target = Vector((CAMERA["target"].x, CAMERA["target"].y, aim))
        cam.rotation_euler = (target - CAMERA["loc"]).to_track_quat("-Z", "Y").to_euler()
    sc.view_settings.exposure = 0.0
    sc.render.resolution_x, sc.render.resolution_y = width, height
    sc.cycles.samples = samples
    sc.render.film_transparent = False
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)


def from_panda_space(p):
    return PANDA_PIVOT + (Vector(p) - PANDA_PIVOT) * PANDA_SCALE


# Rack tom, floor, snare and the other slots the plugin can put a drum in, by how many there
# are: where each lands on the stage and how deep it sits. The factory kit uses the first ones.
SLOTS = {
    "rack1": [(640, 398, -0.22)],
    "rack2": [(712, 410, -0.25), (565, 412, -0.2)],
    "rack3": [(738, 410, -0.25), (640, 395, -0.15), (542, 410, -0.2)],
    "rack4": [(762, 412, -0.25), (682, 396, -0.15), (598, 396, -0.15), (518, 412, -0.2)],
    "floor": [(432, 520, -0.75), (322, 572, -0.95)],
    "snare": [(800, 505, -1.0), (1060, 575, -1.1)],
    "hihat": [(945, 425, -0.55)],
    "crash": [(950, 222, 0.2), (340, 222, 0.25), (1112, 300, 0.0), (170, 340, 0.0)],
    "ride": [(305, 400, -0.25), (1105, 345, -0.1)],
    "china": [(210, 262, 0.6), (1098, 160, 0.6)],
    "splash": [(815, 150, 0.6), (470, 150, 0.6)],
    "perc": [(1095, 560, -0.6), (190, 565, -0.6)],
}


def px_per_inch(world):
    """Stage pixels of radius per inch of diameter for something at `world`."""
    c, f, r, u = cam_basis()
    return focal_px() * INCH / 2 / (Vector(world) - c).dot(f)


class Layers:
    """Renders one part at a time on a transparent background, trims it and notes where it sits."""

    def __init__(self, sc, outdir, scale, samples):
        self.sc, self.outdir, self.scale = sc, outdir, scale
        self.files = {}
        sc.render.resolution_x, sc.render.resolution_y = STAGE_W * scale, STAGE_H * scale
        sc.cycles.samples = samples
        sc.render.use_border = True
        sc.render.use_crop_to_border = False
        os.makedirs(outdir, exist_ok=True)

    def render(self, name, objs, pad=(24, 24, 24, 24), opaque=False):
        from PIL import Image
        keep = set()
        for ob in objs:
            keep.add(ob)
            keep.update(ob.children_recursive)
        for ob in bpy.data.objects:
            if ob.type in ("LIGHT", "CAMERA", "EMPTY") or ob.get("env"):
                continue
            ob.hide_render = ob not in keep
        sc = self.sc
        sc.render.film_transparent = not opaque
        if opaque:
            sc.render.border_min_x, sc.render.border_max_x, sc.render.border_min_y, sc.render.border_max_y = 0, 1, 0, 1
        else:
            x0, y0, x1, y1 = self.bounds([o for o in keep if o.type in ("MESH", "CURVE")])
            x0, y0, x1, y1 = x0 - pad[0], y0 - pad[1], x1 + pad[2], y1 + pad[3]
            sc.render.border_min_x = max(0.0, x0 / STAGE_W)
            sc.render.border_max_x = min(1.0, x1 / STAGE_W)
            sc.render.border_min_y = max(0.0, 1.0 - y1 / STAGE_H)
            sc.render.border_max_y = min(1.0, 1.0 - y0 / STAGE_H)
        path = os.path.join(self.outdir, "_work", "_render.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = Image.open(path).convert("RGBA")
        if opaque:
            img = img.convert("RGB")
            box = (0, 0, img.width, img.height)
        else:
            alpha = img.getchannel("A").point(lambda a: 255 if a > 10 else 0)
            box = alpha.getbbox() or (0, 0, 1, 1)
            # Keep whole design pixels so the 1x and 2x copies line up.
            box = (box[0] // self.scale * self.scale, box[1] // self.scale * self.scale,
                   -(-box[2] // self.scale) * self.scale, -(-box[3] // self.scale) * self.scale)
            img = img.crop(box)
        ext = "jpg" if opaque else "png"
        img.save(os.path.join(self.outdir, "%s@2x.%s" % (name, ext)), quality=90) if opaque else img.save(os.path.join(self.outdir, "%s@2x.png" % name), optimize=True)
        small = img.resize((img.width // self.scale, img.height // self.scale), Image.LANCZOS)
        small.save(os.path.join(self.outdir, "%s.%s" % (name, ext)), quality=90) if opaque else small.save(os.path.join(self.outdir, "%s.png" % name), optimize=True)
        os.remove(path)
        info = dict(file=name, x=box[0] / self.scale, y=box[1] / self.scale, w=img.width / self.scale, h=img.height / self.scale)
        self.files[name] = info
        print("layer", name, info, flush=True)
        return info

    @staticmethod
    def bounds(objs):
        bpy.context.view_layer.update()      # matrices set by hand aren't evaluated until now
        dg = bpy.context.evaluated_depsgraph_get()
        xs, ys = [], []
        for ob in objs:
            ev = ob.evaluated_get(dg)
            for corner in ev.bound_box:
                x, y = project(ev.matrix_world @ Vector(corner))
                xs.append(x)
                ys.append(y)
        return min(xs), min(ys), max(xs), max(ys)


def remove(objs):
    for ob in objs:
        for child in list(ob.children_recursive):
            bpy.data.objects.remove(child, do_unlink=True)
        bpy.data.objects.remove(ob, do_unlink=True)


def ellipse_of(points):
    """Centre and radii of the screen ellipse through projected rim points."""
    pts = [project(p) for p in points]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round((min(xs) + max(xs)) / 2, 2), round((min(ys) + max(ys)) / 2, 2),
            round((max(xs) - min(xs)) / 2, 2), round((max(ys) - min(ys)) / 2, 2)]


def rim(centre, r, tilt, side, n=64, axis="z"):
    rot = Euler((math.radians(tilt), math.radians(side), 0)).to_matrix()
    if axis == "y":
        return [centre + Vector((r * math.cos(2 * math.pi * k / n), 0, r * math.sin(2 * math.pi * k / n))) for k in range(n)]
    return [centre + rot @ Vector((r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), 0)) for k in range(n)]


def P(v):
    return [round(v[0], 2), round(v[1], 2)]


def merge(old, new):
    """new over old, recursively; lists of the same length merge item by item."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = dict(old)
        for k, v in new.items():
            out[k] = merge(old[k], v) if k in old else v
        return out
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [merge(a, b) for a, b in zip(old, new)]
    return new


def layers(outdir, scale=2, samples=64, only=None):
    sc = reset()
    work = os.path.join(outdir, "_work")      # scratch files (the kick logo), not shipped
    os.makedirs(work, exist_ok=True)
    M = Mats(work)
    stage = build_stage(M)
    lights_and_camera(sc)
    sc.view_settings.exposure = 0.0
    L = Layers(sc, outdir, scale, samples)
    want = lambda name: only is None or any(name.startswith(o) for o in only)
    man = dict(stage=dict(w=STAGE_W, h=STAGE_H), files=L.files, kit={}, slots={}, panda={})
    # The heart lights, so the plugin can make them glow and twinkle.
    man["stage"]["bulbs"] = [dict(at=P(project(p)), colour=list(c)) for p, c in BULBS]

    # The room stays in every layer for its light (the pink bounce) but only shows in its own.
    if want("stage"):
        L.render("stage", stage, opaque=True)
    for ob in stage:
        ob["env"] = True
        ob.visible_camera = False
        ob.visible_shadow = False       # the room's bamboo and lights don't shade the parts

    # ---- slots
    for kind, slots in SLOTS.items():
        man["slots"][kind] = [dict(at=[x, y], ppi=round(px_per_inch(at_screen(x, y, d)), 4)) for x, y, d in slots]
    man["slots"]["kick"] = [dict(at=P(project(KICK["pos"] - Vector((0, KICK["depth"] * INCH / 2, 0)))),
                                 ppi=round(px_per_inch(KICK["pos"] - Vector((0, KICK["depth"] * INCH / 2, 0))), 4))]

    # ---- drums, in every wrap
    kick_front = KICK["pos"] - Vector((0, KICK["depth"] * INCH / 2, 0))
    r = KICK["size"] * INCH / 2
    man["kit"]["kick"] = dict(anchor=P(project(kick_front)), radius=round(project(kick_front + Vector((r, 0, 0)))[0] - project(kick_front)[0], 2),
                              size=KICK["size"], head=ellipse_of(rim(kick_front, r * 0.975, 0, 0, axis="y")), wraps={})
    for wrap in WRAPS:
        if want("kick_" + wrap):
            objs = kick(M, wrap)
            man["kit"]["kick"]["wraps"][wrap] = L.render("kick_" + wrap, objs, pad=(24, 24, 24, 24))["file"]
            remove(objs)
    for kind, name in (("tom", "tom1"), ("floor", "tom3"), ("snare", "snare")):
        spec = DRUMS[name]
        pos = place(spec)
        r = spec["size"] * INCH / 2
        rot = Euler((math.radians(spec["tilt"]), math.radians(spec["side"]), 0)).to_matrix()
        bottom = pos + rot @ Vector((0, 0, -spec["depth"] * INCH))
        man["kit"][kind] = dict(anchor=P(project(pos)), radius=round(ellipse_of(rim(pos, r, spec["tilt"], spec["side"]))[2], 2),
                                size=spec["size"], depth=spec["depth"], shell=round(project(bottom)[1] - project(pos)[1], 2),
                                head=ellipse_of(rim(pos, r * 0.985, spec["tilt"], spec["side"])), wraps={})
        for wrap in WRAPS:
            if want("%s_%s" % (kind, wrap)):
                objs = drum(M, name, spec, wrap=wrap, mount=False)
                man["kit"][kind]["wraps"][wrap] = L.render("%s_%s" % (kind, wrap), objs, pad=(24, 24, 24, 24))["file"]
                remove(objs)

    # ---- cymbals (discs on their own: they swing) and their stands per slot
    for kind, name in (("crash", "crash1"), ("ride", "ride"), ("china", "china"), ("splash", "splash")):
        spec = CYMBALS[name]
        c = place(spec)
        r = spec["size"] * INCH / 2
        disc_kind = "china" if kind == "china" else "ride" if kind == "ride" else "crash"
        man["kit"][kind] = dict(anchor=P(project(c)), size=spec["size"], ellipse=ellipse_of(rim(c, r, spec["tilt"], spec["side"])))
        man["kit"][kind]["radius"] = man["kit"][kind]["ellipse"][2]
        if want(kind):
            objs = [cymbal_disc(M, name, c, r, spec["tilt"], spec["side"], disc_kind)]
            man["kit"][kind]["file"] = L.render(kind, objs, pad=(16, 16, 16, 16))["file"]
            remove(objs)
    man["kit"]["stands"] = {}
    for kind in ("crash", "ride", "china", "splash"):
        man["kit"]["stands"][kind] = []
        for i, (x, y, d) in enumerate(SLOTS[kind]):
            c = at_screen(x, y, d)
            boom = 1.0 if kind == "splash" else None
            info = dict(top=P(project(c)))
            if want("stand_%s%d" % (kind, i)):
                objs = stand(M, c, boom=boom, name="%s%d_stand" % (kind, i))
                info["file"] = L.render("stand_%s%d" % (kind, i), objs, pad=(24, 24, 24, 24))["file"]
                remove(objs)
            man["kit"]["stands"][kind].append(info)

    # ---- hi-hat: top and bottom cymbals and the stand
    c = place(HIHAT)
    r = HIHAT["size"] * INCH / 2
    man["kit"]["hihat"] = dict(anchor=P(project(c)), size=HIHAT["size"], top=P(project(c + Vector((0, 0, 0.05)))),
                               bottom=P(project(c - Vector((0, 0, 0.03)))), ellipse=ellipse_of(rim(c, r, 16, -4)))
    man["kit"]["hihat"]["radius"] = man["kit"]["hihat"]["ellipse"][2]
    if want("hat"):
        objs = hihat(M)
        top, bottom, rest = objs[0], objs[1], objs[2:]
        man["kit"]["hihat"]["top_file"] = L.render("hat_top", [top], pad=(16, 16, 16, 16))["file"]
        man["kit"]["hihat"]["bottom_file"] = L.render("hat_bottom", [bottom], pad=(16, 16, 16, 16))["file"]
        man["kit"]["hihat"]["stand_file"] = L.render("hat_stand", rest, pad=(24, 24, 24, 24))["file"]
        remove(objs)

    # ---- the panda, part by part
    pan = man["panda"]
    head_c = from_panda_space(HEAD)
    pan["head"] = dict(anchor=P(project(head_c)), radius=round(project(head_c + Vector((HEAD_R[0] * PANDA_SCALE, 0, 0)))[0] - project(head_c)[0], 2))
    pan["shoulders"] = [P(project(from_panda_space(shoulder(s)))) for s in (-1, 1)]
    pan["cheeks"] = [P(project(from_panda_space(on_head(0.66 * s, -0.38, out=0.02)))) for s in (-1, 1)]
    if want("body"):
        objs = build_body(M, sleeves=False)
        scale_panda(objs)
        pan["body"] = L.render("body", objs, pad=(30, 30, 30, 30))["file"]
        remove(objs)
    pan["sleeves"] = []
    for s in (-1, 1):
        info = dict(pivot=P(project(from_panda_space(shoulder(s)))),
                    end=P(project(from_panda_space(shoulder(s) - Vector((0, 0, SLEEVE_LEN))))))
        if want("sleeve_" + ("l" if s < 0 else "r")):
            objs = build_sleeve_part(M, s)
            scale_panda(objs)
            info["file"] = L.render("sleeve_%s" % ("l" if s < 0 else "r"), objs, pad=(20, 20, 20, 20))["file"]
            remove(objs)
        pan["sleeves"].append(info)
    pan["ears"] = []
    for s in (-1, 1):
        info = dict(pivot=P(project(from_panda_space(ear_pivot(s)))))
        if want("ear_" + ("l" if s < 0 else "r")):
            objs = [build_ear(M, s)]
            scale_panda(objs)
            info["file"] = L.render("ear_%s" % ("l" if s < 0 else "r"), objs, pad=(20, 20, 20, 20))["file"]
            remove(objs)
        pan["ears"].append(info)
    pan["heads"] = {}
    for expr in EXPRESSIONS + ["blink"]:
        if want("head_" + expr):
            objs = build_head(M, expr, ears=False)
            scale_panda(objs)
            pan["heads"][expr] = L.render("head_" + expr, objs, pad=(24, 24, 24, 24))["file"]
            remove(objs)

    # Arm parts lie flat across the frame in front of the body: the plugin turns and stretches them.
    y = to_panda_space(Vector((0, -0.3, 0))).y
    a, b = Vector((-1.6, y, 3.0)), Vector((-0.6, y, 3.0))
    seg = dict(a=P(project(from_panda_space(a))), b=P(project(from_panda_space(b))),
               thickness=round(2 * (project(from_panda_space(a + Vector((0, 0, ARM_R))))[1] - project(from_panda_space(a))[1]) * -1, 2))
    pan["arm"] = seg
    if want("arm"):
        objs = [fur_tube(M, "arm_part", [a, (a + b) / 2, b], ARM_R, fur=900, seed=10)]
        for k, end in enumerate((a, b)):
            cap = sphere("arm_cap%d" % k, end, (ARM_R,) * 3, M.black)
            add_fur(cap, count=260, length=0.055, children=18, seed=20 + k)
            objs.append(cap)
        scale_panda(objs)
        pan["arm"]["file"] = L.render("arm", objs, pad=(20, 20, 20, 20))["file"]
        remove(objs)
    paw_c = Vector((0.6, y, 3.0))
    pan["paw"] = dict(centre=P(project(from_panda_space(paw_c))), dir=[1.0, 0.0])
    if want("paw"):
        objs = build_paw(M, "paw", paw_c, Vector((1, 0, 0)))
        scale_panda(objs)
        pan["paw"]["file"] = L.render("paw", objs, pad=(20, 20, 20, 20))["file"]
        remove(objs)
    butt, tip = Vector((-1.2, y - 0.4, 1.4)), Vector((-1.2 + STICK["length"], y - 0.4, 1.4))
    pan["stick"] = dict(butt=P(project(from_panda_space(butt))), tip=P(project(from_panda_space(tip))))
    if want("stick"):
        objs = build_stick(M, "stick", butt, tip)
        scale_panda(objs)
        pan["stick"]["file"] = L.render("stick", objs, pad=(16, 16, 16, 16))["file"]
        remove(objs)

    path = os.path.join(outdir, "manifest.json")
    if only is not None and os.path.exists(path):
        # A partial run: keep what the last run wrote, update what was rendered now.
        with open(path) as f:
            man = merge(json.load(f), man)
    with open(path, "w") as f:
        json.dump(man, f, indent=1)
    print("wrote", path)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if args and args[0] == "preview":
        w = int(args[2]) if len(args) > 2 else STAGE_W
        h = int(args[3]) if len(args) > 3 else STAGE_H
        s = int(args[4]) if len(args) > 4 else 64
        e = args[5] if len(args) > 5 else "happy"
        lens = float(args[6]) if len(args) > 6 else None
        aim = float(args[7]) if len(args) > 7 else None
        preview(os.path.abspath(args[1]), w, h, s, e, lens, aim)
    elif args and args[0] == "layers":
        scale = int(args[2]) if len(args) > 2 else 2
        s = int(args[3]) if len(args) > 3 else 64
        only = args[4].split(",") if len(args) > 4 else None
        layers(os.path.abspath(args[1]), scale, s, only)
    else:
        print(__doc__)
