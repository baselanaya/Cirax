"""Blender batch exporter used by the Cirax blender engine.

    blender --background model.blend --python cirax_export.py -- GLB /out/model.glb

The first arg after `--` is the target format, the second the output path.
Exports the whole scene; runs inside Blender's bundled Python (bpy).
"""

import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) < 2:
    raise SystemExit("usage: --python cirax_export.py -- FORMAT /out/model.ext")

fmt, out = argv[0].upper(), argv[1]

if fmt == "GLB":
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB")
elif fmt == "GLTF":
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLTF_EMBEDDED")
elif fmt == "FBX":
    bpy.ops.export_scene.fbx(filepath=out)
elif fmt == "OBJ":
    bpy.ops.wm.obj_export(filepath=out)
elif fmt == "STL":
    bpy.ops.wm.stl_export(filepath=out)
elif fmt == "PLY":
    bpy.ops.wm.ply_export(filepath=out)
elif fmt == "X3D":
    bpy.ops.export_scene.x3d(filepath=out)
else:
    raise SystemExit(f"cirax_export: unsupported format {fmt}")

print(f"cirax_export: wrote {out} ({fmt})")
