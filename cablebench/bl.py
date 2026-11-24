"""Small Blender helpers: meshes, materials, text, lights, camera."""
from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Vector


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------
class NT:
    """Tiny node-tree builder."""

    def __init__(self, name):
        self.mat = bpy.data.materials.new(name)
        try:
            self.mat.use_nodes = True
        except Exception:
            pass
        self.nt = self.mat.node_tree
        self.nt.nodes.clear()
        self.out = self.node("ShaderNodeOutputMaterial")
        self.bsdf = None

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def principled(self, **inputs):
        b = self.node("ShaderNodeBsdfPrincipled")
        set_inputs(b, inputs)
        self.link(b.outputs[0], self.out.inputs["Surface"])
        self.bsdf = b
        return b

    def texcoord(self):
        return self.node("ShaderNodeTexCoord")

    def noise(self, vec, scale=5.0, detail=6.0, rough=0.55, dist=0.0):
        n = self.node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        if "Distortion" in n.inputs:
            n.inputs["Distortion"].default_value = dist
        if vec is not None:
            self.link(vec, n.inputs["Vector"])
        return n

    def ramp(self, fac, stops):
        r = self.node("ShaderNodeValToRGB")
        cr = r.color_ramp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (pos, col) in zip(cr.elements, stops):
            el.position = pos
            el.color = tuple(col) + ((1.0,) if len(col) == 3 else ())
        self.link(fac, r.inputs["Fac"])
        return r

    def mix(self, fac, a, b, blend="MIX"):
        m = self.node("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = blend
        _set_or_link(self, m.inputs[0], fac)
        _set_or_link(self, m.inputs[6], a)
        _set_or_link(self, m.inputs[7], b)
        return m.outputs[2]

    def math(self, op, a, b=None):
        m = self.node("ShaderNodeMath", operation=op)
        _set_or_link(self, m.inputs[0], a)
        if b is not None:
            _set_or_link(self, m.inputs[1], b)
        return m.outputs[0]

    def bump(self, height, strength=0.2, distance=0.02):
        b = self.node("ShaderNodeBump")
        b.inputs["Strength"].default_value = strength
        if "Distance" in b.inputs:
            b.inputs["Distance"].default_value = distance
        self.link(height, b.inputs["Height"])
        return b.outputs["Normal"]

    def mapping(self, vec, scale=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0)):
        m = self.node("ShaderNodeMapping")
        m.inputs["Scale"].default_value = scale
        m.inputs["Location"].default_value = loc
        m.inputs["Rotation"].default_value = rot
        self.link(vec, m.inputs["Vector"])
        return m.outputs[0]


def _set_or_link(nt, sock, val):
    if hasattr(val, "is_linked") or isinstance(val, bpy.types.NodeSocket):
        nt.link(val, sock)
    elif isinstance(val, (tuple, list)):
        sock.default_value = tuple(val) + ((1.0,) if len(val) == 3 else ())
    else:
        sock.default_value = val


ALIASES = {
    "Emission": "Emission Color",
    "Subsurface": "Subsurface Weight",
    "Transmission": "Transmission Weight",
    "Coat": "Coat Weight",
    "Sheen": "Sheen Weight",
    "Specular": "Specular IOR Level",
}


def set_inputs(node, inputs):
    for k, v in inputs.items():
        k = ALIASES.get(k, k)
        sock = node.inputs[k]
        if isinstance(v, bpy.types.NodeSocket):
            node.id_data.links.new(v, sock)
        elif isinstance(v, (tuple, list)) and len(v) == 3 and sock.type == "RGBA":
            sock.default_value = tuple(v) + (1.0,)
        else:
            sock.default_value = v


def simple_mat(name, color, rough=0.5, metal=0.0, **kw):
    nt = NT(name)
    nt.principled(**{"Base Color": color, "Roughness": rough, "Metallic": metal, **kw})
    return nt.mat


def emissive(name, color, strength=8.0):
    nt = NT(name)
    e = nt.node("ShaderNodeEmission")
    e.inputs["Color"].default_value = tuple(color) + (1,)
    e.inputs["Strength"].default_value = strength
    nt.link(e.outputs[0], nt.out.inputs["Surface"])
    return nt.mat


# ----------------------------------------------------------------------------
# geometry
# ----------------------------------------------------------------------------
def mesh_obj(name, verts, faces, uvs=None, smooth=True, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        loop_uv = np.zeros((len(me.loops), 2))
        vi = np.zeros(len(me.loops), dtype=int)
        me.loops.foreach_get("vertex_index", vi)
        # uvs given per face-corner list (same order as faces flattened)
        flat = np.asarray(uvs, float).reshape(-1, 2)
        if len(flat) == len(me.loops):
            loop_uv = flat
        else:
            loop_uv = flat[vi]
        uvl.data.foreach_set("uv", loop_uv.ravel())
    me.update()
    if smooth:
        me.shade_smooth() if hasattr(me, "shade_smooth") else None
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    if mat is not None:
        ob.data.materials.append(mat)
    return link(ob)


def tube(name, pts, radius, ring=14, mat=None, cap=True):
    """Tube mesh along a 3D polyline with parallel-transport frames and UVs."""
    P = np.asarray(pts, float)
    n = len(P)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    up = np.array([0, 0, 1.0])
    N = np.zeros_like(P)
    n0 = up - T[0] * (T[0] @ up)
    if np.linalg.norm(n0) < 1e-6:
        n0 = np.array([0, 1.0, 0])
    N[0] = n0 / np.linalg.norm(n0)
    for k in range(1, n):
        v = N[k - 1] - T[k] * (T[k] @ N[k - 1])
        N[k] = v / np.linalg.norm(v)
    B = np.cross(T, N)
    ang = np.linspace(0, 2 * math.pi, ring, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rad = np.broadcast_to(np.asarray(radius, float), (n,))
    V = P[:, None, :] + rad[:, None, None] * (ca[None, :, None] * N[:, None, :] + sa[None, :, None] * B[:, None, :])
    V = V.reshape(-1, 3)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    faces, uvs = [], []
    circ = 2 * math.pi * float(np.mean(rad))
    for k in range(n - 1):
        for j in range(ring):
            j2 = (j + 1) % ring
            a, b, c, d = k * ring + j, k * ring + j2, (k + 1) * ring + j2, (k + 1) * ring + j
            faces.append((a, b, c, d))
            u0, u1 = s[k] / circ, s[k + 1] / circ
            v0, v1 = j / ring, (j + 1) / ring
            uvs += [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]
    verts = list(V)
    if cap:
        for end, k in ((0, 0), (1, n - 1)):
            c = len(verts)
            verts.append(P[k])
            for j in range(ring):
                j2 = (j + 1) % ring
                a, b = k * ring + j, k * ring + j2
                faces.append((c, b, a) if end == 0 else (c, a, b))
                uvs += [(0, 0), (0, 0), (0, 0)]
    return mesh_obj(name, verts, faces, uvs=uvs, mat=mat)


def box(name, center, size, mat=None, bevel=0.0, segments=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        m = ob.modifiers.new("bev", "BEVEL")
        m.width = bevel
        m.segments = segments
        m.limit_method = "ANGLE"
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def cylinder(name, center, radius, depth, axis="Z", mat=None, verts=32, bevel=0.0):
    rot = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=center, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    for p in ob.data.polygons:
        p.use_smooth = True
    if bevel > 0:
        m = ob.modifiers.new("bev", "BEVEL")
        m.width = bevel
        m.segments = 2
        m.limit_method = "ANGLE"
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def torus(name, center, R, r, axis="Z", mat=None):
    rot = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=center, rotation=rot,
                                     major_segments=40, minor_segments=14)
    ob = bpy.context.active_object
    ob.name = name
    for p in ob.data.polygons:
        p.use_smooth = True
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def sphere(name, center, radius, mat=None, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=center, segments=32, ring_count=16)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    for p in ob.data.polygons:
        p.use_smooth = True
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def text(name, body, loc, size, mat=None, align="CENTER", extrude=0.004, rot=(0, 0, 0), font=None, valign="CENTER"):
    cu = bpy.data.curves.new(name, type="FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = valign
    cu.extrude = extrude
    if font is not None:
        cu.font = font
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = rot
    if mat is not None:
        ob.data.materials.append(mat)
    return link(ob)


def ribbon(name, pts2d, width, z, mat=None):
    """Flat strip of given width along a 2D polyline (mitred corners)."""
    P = np.asarray(pts2d, float)
    n = len(P)
    T = np.zeros_like(P)
    T[1:-1] = P[2:] - P[:-2]
    T[0] = P[1] - P[0]
    T[-1] = P[-1] - P[-2]
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    N = np.column_stack([-T[:, 1], T[:, 0]])
    # mitre length correction
    scale = np.ones(n)
    for k in range(1, n - 1):
        a = P[k] - P[k - 1]; b = P[k + 1] - P[k]
        a /= np.linalg.norm(a) + 1e-12; b /= np.linalg.norm(b) + 1e-12
        scale[k] = 1 / max(math.cos(math.acos(np.clip(a @ b, -1, 1)) / 2), 0.4)
    L = P + N * (width / 2 * scale)[:, None]
    R = P - N * (width / 2 * scale)[:, None]
    verts = [(x, y, z) for x, y in L] + [(x, y, z) for x, y in R]
    faces = [(k, k + 1, n + k + 1, n + k) for k in range(n - 1)]
    return mesh_obj(name, verts, faces, smooth=False, mat=mat)


def poly_prism(name, pts2d, z0, z1, mat=None):
    """Extruded 2D polygon (for symbol icons)."""
    P = np.asarray(pts2d, float)
    n = len(P)
    verts = [(x, y, z0) for x, y in P] + [(x, y, z1) for x, y in P]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for k in range(n):
        k2 = (k + 1) % n
        faces.append((k, k2, n + k2, n + k))
    return mesh_obj(name, verts, faces, smooth=False, mat=mat)


# ----------------------------------------------------------------------------
# lights / camera / render
# ----------------------------------------------------------------------------
def area_light(name, loc, target, energy, size, color=(1, 1, 1), shape="DISK"):
    li = bpy.data.lights.new(name, "AREA")
    li.energy = energy
    li.size = size
    li.shape = shape
    li.color = color
    ob = link(bpy.data.objects.new(name, li))
    ob.location = loc
    look_at(ob, target)
    return ob


def point_light(name, loc, energy, color=(1, 1, 1), radius=0.1):
    li = bpy.data.lights.new(name, "POINT")
    li.energy = energy
    li.color = color
    li.shadow_soft_size = radius
    ob = link(bpy.data.objects.new(name, li))
    ob.location = loc
    return ob


def look_at(ob, target, roll=0.0, up=(0, 1, 0)):
    """Point -Z at target, keep the image 'up' aligned with world `up` (no roll)."""
    from mathutils import Matrix
    f = (Vector(target) - ob.location).normalized()
    upv = Vector(up)
    if abs(f.dot(upv)) > 0.999:
        upv = Vector((0, 0, 1))
    right = f.cross(upv).normalized()
    upc = right.cross(f).normalized()
    m = Matrix((right, upc, -f)).transposed()
    ob.rotation_euler = m.to_euler()
    if roll:
        ob.rotation_euler.rotate_axis("Z", roll)


def world(color=(0.02, 0.02, 0.025), strength=1.0, gradient=None):
    w = bpy.data.worlds.new("World")
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = tuple(color) + (1,)
    bg.inputs["Strength"].default_value = strength
    out = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs[0])
    bpy.context.scene.world = w
    return w


def camera(loc, target, lens=50, roll=0.0):
    cam = bpy.data.cameras.new("Camera")
    cam.lens = lens
    cam.sensor_width = 36
    ob = link(bpy.data.objects.new("Camera", cam))
    ob.location = loc
    look_at(ob, target, roll)
    bpy.context.scene.camera = ob
    return ob


def setup_render(res=(1600, 900), samples=48, exposure=0.0, look="AgX - Medium High Contrast"):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    import os
    want = os.environ.get("CABLEBENCH_DEVICE", "CPU").upper()
    if want in ("GPU", "OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ([want] if want != "GPU" else ["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"]):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == kind]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type == kind
                    sc.cycles.device = "GPU"
                    print(f"[cablebench] rendering on {kind}: {[d.name for d in devs]}")
                    break
            except Exception:
                continue
        else:
            print("[cablebench] no GPU found, falling back to CPU")
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 3
    sc.cycles.transmission_bounces = 6
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.exposure = exposure
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = look
    except Exception:
        pass
    sc.render.threads_mode = "AUTO"


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def project(points):
    """World points -> pixel coordinates (x right, y down) with the scene camera."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    cam = sc.camera
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    out = []
    for p in points:
        v = world_to_camera_view(sc, cam, Vector(p))
        out.append((v.x * rx, (1 - v.y) * ry, v.z))
    return out
