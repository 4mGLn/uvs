---
name: unified-video-studio
description: Plan, render, assemble and QA videos end-to-end — storyboard first, one engine per shot (built-in FFmpeg title/image cards, HyperFrames/GSAP, Remotion, Blender, Manim, ComfyUI, existing footage), then FFmpeg assembly with voiceover, music, captions, loudness normalization and an automated quality gate. Use for any video request: promo/홍보영상, explainer, tutorial, motion graphics, kinetic typography, shorts/릴스, 3D shot, math animation, subtitle/자막 burn-in, 영상 제작, 영상 편집, cutting existing footage.
---

# Unified Video Studio

The skill coordinates engines; it does not install them. Paths below are relative to
this skill's directory (`scripts/`, `references/`, `templates/`). Every script prints
`--help`, exits non-zero on failure and reports errors without a traceback.

## Workflow

1. **Brief.** Collect goal, audience, duration, language, aspect ratio/platform, brand,
   asset rights, deadline. Unspecified defaults: 30 s, Korean, 1920x1080, 30 fps,
   -14 LUFS. Ask (one question) only when the answer changes the storyboard.
2. **Environment.** `python3 scripts/init_project.py <project> [--aspect 9:16] [--duration 15]`
   creates the project and runs `scripts/doctor.py`. Read `qa/environment.json`; never
   say an engine is available unless doctor reports it ready.
3. **Storyboard.** Edit `<project>/storyboard.json` (schema below). Choose ONE engine per
   shot with `references/ROUTING.md`; prefer `ffmpeg-title`/`image` when they are good
   enough, and fall back to them when an engine is not ready. Run
   `python3 scripts/validate.py --project <project>` until it passes.
4. **Animatic first.** `python3 scripts/build.py --project <project> --placeholders`
   renders built-in shots plus labeled placeholders for the rest, so timing can be
   reviewed before any expensive render. Show the user the contact sheet
   (`qa/frames/contact_sheet.jpg`) when direction is uncertain.
5. **Render real shots.** For each non-built-in shot, follow
   `references/engines/<engine>.md` (contract: `references/engines/_contract.md`) and write the clip to
   `<project>/renders/clips/<shot-id>.mp4` at the brief's size/fps and the shot's
   duration. A real clip automatically replaces its placeholder.
6. **Voice and captions (optional).** `scripts/tts.py` writes per-shot voice files
   (edge-tts sends text to Microsoft — get consent — or `--provider cmd` for a local
   TTS). Captions come from the storyboard (`make_captions.py`, run by build), or from
   WhisperX for real speech timing (`references/engines/footage.md`).
7. **Final build.** `python3 scripts/build.py --project <project> [--burn-subs]
   [--music <file> --duck]`. Loudness normalization is automatic when voice or music exists.
8. **QA and handoff.** Build ends with `quality_gate.py`. Fix every error. Look at every
   image in `qa/frames/` (typos, Hangul rendering, safe areas — FFmpeg cannot judge these).
   Hand over: final MP4 path, `qa/qa_report.json` summary, open warnings, and
   `provenance.json` (fill tools, assets, models, seeds, prompts, voices, music, licenses).

Do not publish or upload anything without explicit user authorization.

## Storyboard schema (`storyboard.json`)

```jsonc
{"shots": [{
  "id": "shot-001",              // [A-Za-z0-9_-], becomes the clip file name
  "duration_s": 5,                // end-to-end, rounded to whole frames; start_s optional, checked if present
  "engine": "ffmpeg-title",       // ffmpeg-title | image | footage | hyperframes | remotion | blender | manim | comfyui
  "on_screen_text": "핵심 메시지", // title text / lower third (image) / placeholder label
  "voiceover": "내레이션 문장.",    // drives TTS and script-timed captions
  "visual_direction": "...", "purpose": "hook",
  "style": {"bg": "#101820", "fg": "#FFFFFF", "accent": "#F2AA4C", "subtitle": "보조 문구",
            "font_size": 96, "align": "center", "motion": "zoom"},
  "assets": [{"path": "assets/x.png", "type": "image", "source": "...", "license": "..."}],
  "clip": "assets/footage.mp4",   // optional explicit clip (required for engine footage)
  "voiceover_audio": "assets/voice/custom.wav", "voiceover_offset_s": 0.15,
  "transition": "fade", "transition_s": 0.6   // cut | fade (through black at the end of this shot)
}]}
```

## Scripts

| Script | Purpose |
|---|---|
| `init_project.py` | project skeleton + templates + environment report |
| `doctor.py` | required tools, Hangul font, engines ready, GPU/VRAM, versions |
| `validate.py` | brief/storyboard schema, timeline, VO speed, provenance; `--check-clips` |
| `render_builtin.py` | `ffmpeg-title` and `image` shots; `--placeholders` for the rest |
| `tts.py` | per-shot voice files (`edge` or any local command) |
| `make_captions.py` | script-timed SRT from voiceover text |
| `assemble.py` | conform shots to duration, fades, voice mix, music+ducking, subtitle burn-in, loudnorm; also plain `a.mp4 b.mp4 -o out.mp4` |
| `quality_gate.py` | format/duration/fps, black/silence/freeze, LUFS/true peak, caption checks, review frames, JSON report |
| `build.py` | validate → render → captions → assemble → QA in one command |
| `tests/smoke_test.py` | end-to-end self-test using only FFmpeg |

## Rules

- One timeline engine per shot; render shots independently and assemble with FFmpeg.
- Deterministic rendering: frame-based animation (Remotion `useCurrentFrame`, Manim,
  Blender keyframes); fixed seeds for generative shots. Record versions/seeds/prompts.
- Rights: confirm licenses for music, fonts, images, models and software (e.g. Remotion
  needs a company license above its free tier; model weights carry their own terms).
- Keep Korean text inside safe areas and within ~20 chars per caption line;
  `validate.py` and `quality_gate.py` warn when it is not.
- Project layout: `scenes/` (engine sources), `assets/` (inputs, `voice/`),
  `renders/clips/`, `renders/placeholders/`, `renders/final.mp4`, `captions/`, `qa/`.
