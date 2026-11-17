# Changelog

## 2.2.0 — 2026-11-17
### Added
- install.sh offers to install missing tools: per-tool prompt in an interactive terminal (default no, sizes shown); `--with ffmpeg,blender,manim,auto-editor,whisperx,edge-tts|all` for agents and pipes; `--no-extras` to opt out. Python tools via `uv tool install`, FFmpeg/Blender/Manim libraries via apt or Homebrew; sudo only from a terminal or with a cached password, otherwise the command is printed. ComfyUI is never installed automatically
- CI installs auto-editor through `--with` to exercise the path

## 2.1.1 — 2026-11-17
### Fixed
- install.sh put backups as `<skill>.bak-<timestamp>` inside agent skills folders, where agents loaded them as a duplicate skill. Older copies of this skill are now replaced; unrelated folders move to `~/.agents/.uvs-backups/<timestamp>/`
- doctor.py reported TTS as unavailable although `tts.py` works through `uvx`; ComfyUI line now states it checks VRAM only; a hint explains what `--` means

## 2.1.0 — 2026-11-17
Agent-agnostic distribution (was Claude Code-first).

### Changed
- `install.sh` installs to the shared `~/.agents/skills/` (or `./.agents/skills/` with `--project`) and symlinks into detected agents: Claude Code (`~/.claude/skills`, project `.claude/skills`), Codex (`$CODEX_HOME/skills`); `--link DIR` (repeatable), `--copy`, `--no-link`; upgrades replace the previous install in place; uninstall also removes the links/copies it created; relative symlinks
- README: agent-neutral install guide and copy-paste prompts; Claude plugin marketplace is now an optional channel

### Added
- `AGENTS.md` with `CLAUDE.md` and `AGENT.md` symlinks; `.agents/skills/unified-video-studio` symlink for in-repo discovery
- CI checks the agent links with a throwaway HOME

## 2.0.0 — 2026-11-17
Made the skill usable end-to-end with FFmpeg alone; scripts now implement what SKILL.md describes.

### Added
- Public repository with `install.sh` (curl one-liner, user/project/agents scope, uninstall), Claude Code plugin marketplace manifest, CI smoke test
- `init_project.py` (project skeleton, aspect presets, environment report), `build.py` (one-command pipeline)
- `validate.py`: brief/storyboard schema, timeline continuity, engine/transition values, VO speed, text length, provenance, `--check-clips`
- `render_builtin.py`: Hangul-safe title cards (`ffmpeg-title`), image shots with zoom + lower third (`image`), labeled placeholders for an animatic
- `tts.py` (edge-tts or any local TTS command), `make_captions.py` (script-timed SRT)
- `references/engines/*.md` per-engine render recipes and a shared clip contract; delivery presets in ROUTING.md
- `templates/provenance.json`; richer brief (brand, delivery loudness) and a 4-shot storyboard template
- `tests/smoke_test.py`: FFmpeg-only end-to-end test including failure paths

### Changed
- `assemble.py`: project mode (conform to shot duration, fade transitions, per-shot voice mix), `--fit contain|cover`, `--crf/--preset`, music with ducking, subtitle burn-in, `--loudnorm`; PCM intermediates avoid AAC gaps at cuts; refuses to overwrite inputs; aspect/fps warnings
- `quality_gate.py`: fps, pix_fmt, audio presence, duration vs storyboard, black/silence/freeze detection, integrated LUFS and true peak, caption checks, review frames + contact sheet, JSON report; corrupt files reported without traceback
- `doctor.py`: required vs optional, versions, FFmpeg features, Hangul font, GPU/VRAM, engine readiness, non-zero exit when required items are missing
- SKILL.md: Korean triggers, step-by-step workflow, storyboard schema; routing lives only in ROUTING.md

### Fixed (pre-release review)
- Title/lower-third text containing `%`, `{` or `\` rendered blank or mangled (drawtext `expansion=none`)
- Timeline drift with non-integer frame durations and NTSC rates: segments are cut to frame-exact counts from cumulative shot boundaries; 29.97/23.976/59.94 map to x/1001 rationals
- Clips whose audio outlasts the video left frame gaps (video stream duration is now used)
- validate.py: type checks for text, style, offsets, assets, clip/voiceover_audio paths; fade length checked against both adjacent shots; cut shots shorter than 0.6 s accepted; non-positive size/fps rejected; whole-frame duration warning
- Aspect warning honours rotation metadata; stale captions removed when voiceover text is gone; captions and TTS fit check honour `voiceover_offset_s`
- Vertical projects: smaller, higher burned-in captions clear of Shorts/Reels UI; title text shrinks to fit and sits above the caption zone
- init_project.py keeps sizes even and sets a platform for non-16:9 aspects; build.py exit codes match its docs

## 1.0.0
Initial routing notes, templates and basic FFmpeg assemble/QA scripts.
