# HyperFrames + GSAP (`engine: hyperframes`)

Best for: HTML/CSS-native motion graphics, kinetic typography, UI mockups animated with GSAP.
Needs: Node ≥ 18 and a headless Chromium.

> The HyperFrames CLI is young and changes quickly; this skill has NOT verified its
> commands. Read the current README at https://github.com/heygen-com/hyperframes
> (and its bundled agent skills, if any) before the first render, then record the
> exact version and command in `provenance.json`.

## Rules that apply regardless of version
- Animation must be seekable by frame: build a paused GSAP timeline and let the
  renderer set its time (`tl.pause(); tl.seek(frame / fps)`), never rely on real-time
  playback. GSAP agent skills: https://github.com/greensock/gsap-skills
- Page size = brief `width`x`height`; timeline length = shot `duration_s`.
- Self-host fonts (`@font-face` with a Hangul font file in the scene folder) and
  wait for `document.fonts.ready` before the first frame.
- No network requests during render (inline or bundle images, fonts, data).
- Output to `<project>/renders/clips/<shot-id>.mp4` (see `_contract.md`).

## Fallback when HyperFrames is unavailable
- Same look in Remotion (`remotion.md`) — both are web stacks; port the GSAP timeline
  to `interpolate()` calls.
- Or simplify to an `ffmpeg-title` card for text-only shots.
