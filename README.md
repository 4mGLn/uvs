# uvs — Unified Video Studio

[![smoke](https://github.com/4mGLn/uvs/actions/workflows/smoke.yml/badge.svg)](https://github.com/4mGLn/uvs/actions/workflows/smoke.yml)
![version](https://img.shields.io/badge/version-2.1.0-blue) ![license](https://img.shields.io/badge/license-MIT-green)

An **agent-agnostic** skill (Agent Skills / `SKILL.md` format) for storyboard-driven
video production. It works with Claude Code, Codex and any agent that can read
`SKILL.md` and run shell commands. You describe the video;
the agent writes a storyboard, renders each shot with **one** engine, then assembles
everything with FFmpeg: voiceover, music with ducking, burned-in captions, loudness
normalization. Every build ends with an automated quality gate (QA). Defaults are
Korean-first (Hangul fonts, caption rules, ko TTS voices).

- **Works with FFmpeg alone**: title cards, image shots with slow zoom, footage,
  animatic placeholders, captions, music and QA.
- **Optional engines** (used when `doctor.py` reports them ready): Remotion,
  HyperFrames/GSAP, Blender (+ Blender MCP), Manim, ComfyUI, WhisperX, Auto-Editor, TTS.

## Install

The skill is installed once into the shared folder `~/.agents/skills/unified-video-studio`
and **symlinked** into the skills folder of each agent found on your machine:

| Agent | Detected by | Link created |
|---|---|---|
| any agent reading `~/.agents/skills` | — | (the install itself) |
| Claude Code | `~/.claude` exists | `~/.claude/skills/unified-video-studio` |
| Codex | `$CODEX_HOME` or `~/.codex` exists | `~/.codex/skills/unified-video-studio` |
| anything else | `--link <its skills folder>` | `<dir>/unified-video-studio` |

Agents without a skills feature can still use it: tell them to read `SKILL.md` first.

### 1. Ask your agent (copy & paste)

Paste one of these into your agent (Claude Code, Codex, Gemini CLI, Cursor, …):

```text
Install the "unified-video-studio" agent skill from https://github.com/4mGLn/uvs
(follow the repo's AGENTS.md). Run:
curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
If you don't read ~/.agents/skills, ~/.claude/skills or ~/.codex/skills, re-run it with
`bash -s -- --link <your skills folder>`. Show me the doctor.py and smoke test results.
If FFmpeg or a Hangul font is missing, tell me the install command for my OS and ask
before running it.
```

```text
https://github.com/4mGLn/uvs 의 unified-video-studio 에이전트 스킬을 설치해줘(레포의 AGENTS.md 참고).
curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash 를 실행하고,
네가 ~/.agents/skills, ~/.claude/skills, ~/.codex/skills 를 읽지 않으면
`bash -s -- --link <너의 스킬 폴더>` 로 다시 실행해. doctor와 smoke 테스트 결과를 보여주고,
FFmpeg나 한글 폰트가 없으면 내 OS에 맞는 설치 명령을 알려준 뒤 실행 전에 물어봐.
```

### 2. One-line install (curl)

```bash
curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
```

Options go after `bash -s --`:

| Option | Effect |
|---|---|
| *(none)* | user install: `~/.agents/skills/` + links for detected agents |
| `--project` | current repo only: `./.agents/skills/` (+ `./.claude/skills` link if Claude Code is installed) |
| `--link DIR` | also expose the skill in `DIR` (repeatable), e.g. `--link ~/.gemini/skills` |
| `--copy` | copy instead of symlink, for tools that do not follow symlinks |
| `--no-link` | only the shared install; touch no agent folder |
| `--ref v2.1.0` | install a specific tag or branch |
| `--dir PATH` | custom install folder (no agent links unless `--link`) |
| `--uninstall` | remove the install and the links/copies it created (combine with the same scope options) |

Re-running the installer upgrades in place. Anything else that already sits at a
target path is moved to `<path>.bak-<timestamp>`. Then it runs `doctor.py` and, if
the required tools are present, the FFmpeg-only smoke test. It needs `bash`, `tar`,
`curl` or `wget`, and Python ≥ 3.9. Read [install.sh](install.sh) first if you prefer.

### 3. Manual / no curl

```bash
git clone https://github.com/4mGLn/uvs && bash uvs/install.sh      # same options
```
Or copy `skills/unified-video-studio/` into your agent's skills folder yourself.

### 4. Claude Code plugin marketplace (optional)

```text
/plugin marketplace add 4mGLn/uvs
/plugin install uvs@uvs
```
As a plugin the skill is namespaced `uvs:unified-video-studio`. Use either this or
`install.sh` for Claude Code, not both.

### Requirements

- **FFmpeg** with libx264, aac, drawtext and libass, plus a **Hangul font**:
  - Ubuntu/Debian: `sudo apt install ffmpeg fonts-noto-cjk`
  - macOS: `brew install ffmpeg` (Apple SD Gothic Neo is built in)
  - Windows: `winget install Gyan.FFmpeg` (Malgun Gothic is built in)
- Optional engines: see [ROUTING.md](skills/unified-video-studio/references/ROUTING.md).

## Use

Start a new agent session and ask in plain language:

```text
unified-video-studio로 30초 한국어 SaaS 홍보영상 만들어줘. 1080p, 스토리보드부터 보여주고
대시보드 장면은 Remotion으로, 나머지는 타이틀 카드로. 자막 넣고 QA 리포트까지.
```

```text
Use unified-video-studio to turn assets/demo.mp4 into a 15-second vertical teaser
with burned-in Korean captions and background music at -14 LUFS.
```

The agent:
1. Writes a brief and storyboard.
2. Renders an **animatic** with placeholders so you can review the timing.
3. Renders the real shots.
4. Builds `renders/final.mp4` and shows you `qa/qa_report.json` plus a frame contact sheet.

You can also drive it directly from the command line:

```bash
S=~/.agents/skills/unified-video-studio/scripts
python3 $S/init_project.py myvideo --title "제품 소개" --duration 30   # --aspect 9:16 for Shorts
python3 $S/build.py --project myvideo --placeholders                 # animatic
python3 $S/build.py --project myvideo --burn-subs --music myvideo/assets/music.mp3 --duck
```

## What's inside

```
AGENTS.md                  instructions for agents (CLAUDE.md, AGENT.md -> symlinks)
install.sh                 agent-agnostic installer
.agents/skills/…           symlink so agents opened in this repo discover the skill
.claude-plugin/            optional Claude Code marketplace manifest
skills/unified-video-studio/
  SKILL.md                 agent workflow + storyboard schema
  scripts/                 doctor, init_project, validate, render_builtin, tts,
                           make_captions, assemble, quality_gate, build (stdlib Python + FFmpeg)
  references/ROUTING.md    which engine for which shot, delivery presets
  references/engines/      per-engine render recipes (Remotion, HyperFrames, Blender, Manim, ComfyUI, footage)
  templates/               brief, storyboard, provenance
  tests/smoke_test.py      end-to-end test, FFmpeg only
```

See the [skill README](skills/unified-video-studio/README.md) and the
[CHANGELOG](skills/unified-video-studio/CHANGELOG.md).

## Notes

- The skill does not install engines, model weights or licenses for you. It reports
  what is available and falls back to the built-in shot types.
- `tts.py --provider edge` sends narration text to Microsoft's online TTS service.
  Use `--provider cmd` with a local TTS if that is not acceptable.
- Check the license of every asset, font, model and tool you use (for example, Remotion
  requires a company license above its free tier). Record them in `provenance.json`.
- Nothing is uploaded or published unless you explicitly ask.

## License

[MIT](LICENSE)
