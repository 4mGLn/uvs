# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Gemini CLI, Cursor, and others)
working with this repository. `CLAUDE.md` and `AGENT.md` are symlinks to this file;
edit only `AGENTS.md`.

## What this repo is

`uvs` ships one agent skill, **unified-video-studio**, in the Agent Skills format
(a folder with `SKILL.md` + `scripts/` + `references/`). It is agent-agnostic: any
agent that can read `SKILL.md` and run shell commands can use it.

- Skill source: `skills/unified-video-studio/` (the only copy; everything else links to it)
- `.agents/skills/unified-video-studio` → symlink, so agents opened in this repo discover the skill
- `install.sh` → installs to `~/.agents/skills/` and links it into detected agents' skill folders
- `.claude-plugin/` → optional Claude Code plugin marketplace manifest (one distribution channel among several)

## If a user asks you to install this skill

1. Run `curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash`
   (add `-s -- --project` for the current repo only). Without network piping,
   run `git clone https://github.com/4mGLn/uvs && bash uvs/install.sh`.
2. Show the user the `doctor.py` output and the smoke test result printed by the installer.
3. If FFmpeg or a Hangul font is missing, give the OS-specific command
   (`sudo apt install ffmpeg fonts-noto-cjk`, `brew install ffmpeg`, `winget install Gyan.FFmpeg`)
   and ask before running anything with `sudo`.
4. If your agent does not read `~/.agents/skills`, `~/.claude/skills` or `~/.codex/skills`,
   re-run with `--link <your skills folder>`. If it has no skills feature at all, read
   `~/.agents/skills/unified-video-studio/SKILL.md` at the start of a video task and follow it.

## If a user asks you to make a video

Load `skills/unified-video-studio/SKILL.md` (or the installed copy) and follow its workflow.
Do not improvise a different pipeline.

## Developing this repo

- Scripts are Python ≥ 3.9 **standard library only**, plus `ffmpeg`/`ffprobe`. Do not add dependencies.
- Run before every commit: `python3 -I skills/unified-video-studio/tests/smoke_test.py` (must print `RESULT: PASS`).
- Behaviour described in `SKILL.md` must exist in the scripts; when you change one, update the other.
- Engine routing lives only in `references/ROUTING.md`; per-engine commands only in `references/engines/`.
- Keep the skill free of agent-specific instructions; agent-specific wiring belongs in `install.sh`.
- Release checklist: bump the version in `skills/unified-video-studio/README.md`,
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and the README badge;
  add a `CHANGELOG.md` entry; tag `vX.Y.Z`.
- Test `install.sh` with a throwaway `HOME` (e.g. `HOME=$(mktemp -d) bash install.sh --no-test`)
  so your own agent folders are not modified.
