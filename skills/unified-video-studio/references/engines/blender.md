# Blender (+ Blender MCP) (`engine: blender`)

Best for: 3D product shots, camera moves, stylized 3D scenes.
Needs: Blender (`doctor.py`). Blender MCP lets the agent drive a running Blender
through an add-on; it is a remote control, not a renderer. Setup per
https://github.com/ahujasid/blender-mcp (Blender add-on + MCP server, typically
`uvx blender-mcp`) — verify against its README; don't edit the user's MCP config
without asking.

## Build the scene
- With MCP: create/modify objects, materials, lights and camera through the MCP tools,
  then save to `<project>/scenes/<shot-id>/scene.blend`.
- Without MCP: write a Python script `scenes/<shot-id>/build.py` and run
  `blender -b --python scenes/<shot-id>/build.py`.

## Render (headless, deterministic)
```bash
blender -b scenes/shot-005/scene.blend --python-expr "
import bpy; s=bpy.context.scene
s.render.resolution_x=1920; s.render.resolution_y=1080; s.render.resolution_percentage=100
s.render.fps=30; s.render.fps_base=1.0; s.frame_start=1; s.frame_end=int(4*30)
s.render.image_settings.file_format='PNG'
s.render.filepath='//frames/f_'" -a
ffmpeg -y -framerate 30 -i scenes/shot-005/frames/f_%04d.png \
  -c:v libx264 -pix_fmt yuv420p -crf 18 renders/clips/shot-005.mp4
```
- Render to an image sequence (resumable if it crashes), then encode.
- Eevee is fast; Cycles is slow on small GPUs — on < 6 GB VRAM use Eevee or lower samples.
- Fix seeds for any procedural noise; keep frame range = `duration_s * fps`.
- NTSC rates: 29.97 → `fps=30, fps_base=1.001`; 23.976 → `fps=24, fps_base=1.001` (and `-framerate 30000/1001` / `24000/1001` for ffmpeg).
- Hangul text objects need a font that has Hangul (`bpy.data.fonts.load(path)`).
