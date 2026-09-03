# Engine notes — local AI extras

## piper (text → speech, offline)

Converts plain-text and Markdown files to spoken WAV audio using the
[rhasspy piper](https://github.com/rhasspy/piper) CLI and a voice model.

1. Install the piper binary (Arch: `paru -S piper-tts` / release tarball from
   github.com/rhasspy/piper/releases) so `piper` is on your PATH.
2. Download a voice into the models directory:

       mkdir -p ~/.local/state/cirax/models/piper
       cd ~/.local/state/cirax/models/piper
       curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx
       curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

3. `cirax convert notes.txt narration.wav`

Any piper voice works — drop the `.onnx` + `.onnx.json` pair into the models
directory and point the engine spec's `--model` at it.

## blender (3D export)

`cirax convert suzanne.blend suzanne.glb` runs Blender headless
(`blender --background … --python …`) with the bundled exporter script
(`src/cirax/data/blender/cirax_export.py`), exporting the whole scene to
GLB / GLTF / FBX / OBJ / STL / PLY / X3D.
