# Clip contract (all engines)

Every engine-rendered shot must produce exactly this, or `assemble.py` will conform it
with warnings:

- File: `<project>/renders/clips/<shot-id>.mp4` (or set the shot's `clip` path)
- Size and fps: the brief's `width`, `height`, `fps`
- Length: the shot's `duration_s` (longer is trimmed, shorter holds the last frame)
- Video: H.264, `yuv420p`. Audio optional (silence is added)
- Sources kept in `<project>/scenes/<shot-id>/` so the shot can be re-rendered
- Record tool version, seed, prompt/workflow and asset licenses in `provenance.json`

After rendering: `python3 scripts/validate.py --project <project> --check-clips`.
If an engine is not installed, say so, offer the install steps below or a built-in
fallback (`ffmpeg-title`/`image`) — never pretend a render happened.
