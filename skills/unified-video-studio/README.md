# Unified Video Studio Skill

Version 2.2.0 (2026-11-17). Agent-agnostic skill (SKILL.md format) for storyboard-driven video production:
one engine per shot, FFmpeg assembly, voiceover/music/captions, loudness
normalization and an automated quality gate. Korean-first defaults.

Works out of the box with **FFmpeg + a Hangul font** (title cards, image shots,
footage, animatic placeholders, captions, music, QA). HyperFrames/GSAP, Remotion,
Blender (+MCP), Manim, ComfyUI, WhisperX, Auto-Editor and TTS are optional engines
the skill routes to when `doctor.py` reports them ready.

## Install
```bash
curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
```
Installs to `~/.agents/skills/` and links into detected agents (Claude Code, Codex);
`--link <dir>` for others. Agent prompt, project scope and plugin marketplace: see
https://github.com/4mGLn/uvs. The installer runs `doctor.py` and the smoke test.

Requirements: Python ≥ 3.9 (stdlib only), FFmpeg with libx264/aac/drawtext/libass,
a Hangul font (`sudo apt install fonts-noto-cjk` or `fonts-nanum`; macOS/Windows have one).

## Quick start (manual)
```bash
S=~/.agents/skills/unified-video-studio/scripts
python3 $S/init_project.py myvideo --title "제품 소개" --duration 30
# edit myvideo/storyboard.json
python3 $S/build.py --project myvideo --placeholders     # animatic
# render real clips into myvideo/renders/clips/<shot-id>.mp4, add voice/music
python3 $S/tts.py --project myvideo                      # optional; edge-tts is an online service
python3 $S/build.py --project myvideo --burn-subs --music myvideo/assets/music.mp3 --duck
```
Outputs: `renders/final.mp4`, `qa/qa_report.json`, `qa/frames/*.jpg` (per-shot frames + contact sheet).

## Example prompt
"unified-video-studio로 30초 한국어 SaaS 홍보영상 만들어줘. 1080p, 스토리보드부터 보여주고
타이포는 타이틀 카드로, 대시보드 장면은 Remotion으로. 자막 넣고 QA 리포트까지."

## Plain assembly (no project)
Run from the skill folder:
```bash
python3 scripts/assemble.py intro.mp4 demo.mp4 -o final.mp4 --fit cover --loudnorm
python3 scripts/quality_gate.py final.mp4 --width 1920 --height 1080 --fps 30 --frames-dir qa/
```

## Notes
Not bundled: engines, Blender MCP connections, model weights, credentials, commercial
licenses. `tts.py --provider edge` sends text to Microsoft's online TTS. Verify licenses
of every asset, font, model and tool before production; record them in `provenance.json`.
See CHANGELOG.md for changes.
