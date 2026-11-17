# Engine routing (single source of truth)

Pick ONE engine per shot. Start from the cheapest engine that achieves the shot;
check `doctor.py` "engines" before choosing anything beyond the built-ins.

| Shot need | Engine (`engine` value) | Needs | Detail |
|---|---|---|---|
| Title, statement, CTA, chapter card, simple kinetic text | `ffmpeg-title` (built-in) | FFmpeg + Hangul font | `render_builtin.py` |
| Photo / screenshot with slow zoom + lower third | `image` (built-in) | FFmpeg | `render_builtin.py` |
| Existing footage, interviews, screen recordings | `footage` | FFmpeg (+ Auto-Editor, WhisperX) | `engines/footage.md` |
| Rich 2D motion graphics, UI animation in HTML/CSS/GSAP | `hyperframes` | Node ≥ 18, Chromium | `engines/hyperframes.md` |
| Data viz, dashboards, product promos in React, templated variants | `remotion` | Node ≥ 18 | `engines/remotion.md` |
| 3D product/scene shots | `blender` | Blender (+ Blender MCP to drive it) | `engines/blender.md` |
| Math, algorithms, diagrams that transform | `manim` | Manim CE (+ LaTeX for formulas) | `engines/manim.md` |
| Generative B-roll | `comfyui` | NVIDIA GPU, enough VRAM, model license | `engines/comfyui.md` |

## Decision rules

1. Text-only shot → `ffmpeg-title`, unless the motion itself is the point.
2. Several shots in the same style (e.g. a promo) → one code engine (Remotion **or**
   HyperFrames) for all of them rather than mixing two web stacks.
3. Engine not ready (doctor) → do not install silently. Offer: install steps from the
   engine reference, a built-in fallback, or a placeholder for now.
4. Generative video on < 8 GB VRAM (doctor `gpu`) → recommend a cloud GPU or a still
   `image` shot instead; do not attempt local generation.
5. Shot planning tools (e.g. Video Shotcraft) and alternative orchestrators (e.g.
   OpenMontage) are optional aids; this skill's storyboard + `build.py` stay the pipeline.

## Delivery presets

| Platform | Size | fps | Loudness | Notes |
|---|---|---|---|---|
| YouTube 16:9 | 1920x1080 | 30 (or 24/60) | -14 LUFS | `init_project.py --aspect 16:9` |
| Shorts / Reels / TikTok | 1080x1920 | 30 | -14 LUFS | `--aspect 9:16`; keep text out of bottom ~20% and right edge (UI overlays) |
| Instagram feed | 1080x1350 | 30 | -14 LUFS | `--aspect 4:5` |
| Broadcast (KR/EU) | 1920x1080 | 29.97/25 | -24 LKFS / -23 LUFS | set `brief.delivery.loudness_lufs` |

## External projects (verify before use)

Repository locations and licenses change; check the README and license of the version
you install, and pin it in `provenance.json`.

- Remotion — https://github.com/remotion-dev/remotion (agent skills: remotion-dev/skills)
- GSAP — https://github.com/greensock/GSAP (agent skills: greensock/gsap-skills)
- HyperFrames — https://github.com/heygen-com/hyperframes
- Blender MCP — https://github.com/ahujasid/blender-mcp
- Manim Community — https://github.com/ManimCommunity/manim
- ComfyUI — https://github.com/comfyanonymous/ComfyUI ; Wan 2.x models — https://github.com/Wan-Video
- WhisperX — https://github.com/m-bain/whisperX ; Auto-Editor — https://github.com/WyattBlue/auto-editor
- Optional: Video Shotcraft — https://github.com/Vincentwei1021/video-shotcraft ;
  OpenMontage — https://github.com/OpenMontageInc/OpenMontage (not verified by this skill)
