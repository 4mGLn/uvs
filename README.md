# uvs — Unified Video Studio

[![smoke](https://github.com/4mGLn/uvs/actions/workflows/smoke.yml/badge.svg)](https://github.com/4mGLn/uvs/actions/workflows/smoke.yml)
![version](https://img.shields.io/badge/version-2.0.0-blue) ![license](https://img.shields.io/badge/license-MIT-green)

A Claude Code skill for storyboard-driven video production. You describe the video;
the agent writes a storyboard, renders each shot with **one** engine, then assembles
everything with FFmpeg: voiceover, music with ducking, burned-in captions, loudness
normalization. Every build ends with an automated quality gate (QA). Defaults are
Korean-first (Hangul fonts, caption rules, ko TTS voices).

- **Works with FFmpeg alone**: title cards, image shots with slow zoom, footage,
  animatic placeholders, captions, music and QA.
- **Optional engines** (used when `doctor.py` reports them ready): Remotion,
  HyperFrames/GSAP, Blender (+ Blender MCP), Manim, ComfyUI, WhisperX, Auto-Editor, TTS.

## Install

### 1. Ask your agent (copy & paste)

Paste one of these into Claude Code (or any agent that can run shell commands):

```text
Install the "unified-video-studio" skill from https://github.com/4mGLn/uvs.
Run: curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
Then show me the doctor.py result and the smoke test result. If FFmpeg or a Hangul
font is missing, tell me the exact install command for my OS and ask before running it.
```

```text
https://github.com/4mGLn/uvs 의 unified-video-studio 스킬을 설치해줘.
curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash 를 실행하고
doctor 결과와 smoke 테스트 결과를 보여줘. FFmpeg나 한글 폰트가 없으면 내 OS에 맞는
설치 명령을 알려주고 실행 전에 물어봐.
```

### 2. One-line install (curl)

```bash
curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
```

Options go after `bash -s --`:

| Command | Effect |
|---|---|
| `… \| bash` | install for your user: `~/.claude/skills/unified-video-studio` |
| `… \| bash -s -- --project` | install for the current repo only: `./.claude/skills/unified-video-studio` |
| `… \| bash -s -- --agents` | install to `~/.agents/skills/` (other agent CLIs) |
| `… \| bash -s -- --ref v2.0.0` | install a specific tag or branch |
| `… \| bash -s -- --dir PATH` | install to a custom folder |
| `… \| bash -s -- --uninstall` | remove it |

The installer moves any existing install to a `.bak-<timestamp>` folder. It then runs
`doctor.py`, and the FFmpeg-only smoke test if the required tools are present. It
needs `bash`, `tar`, `curl` or `wget`, and Python ≥ 3.9. Read
[install.sh](install.sh) first if you prefer to.

### 3. Claude Code plugin marketplace

```text
/plugin marketplace add 4mGLn/uvs
/plugin install uvs@uvs
```

As a plugin, the skill is namespaced as `uvs:unified-video-studio`.

### 4. Manual

```bash
git clone https://github.com/4mGLn/uvs && bash uvs/install.sh
```

### Requirements

- **FFmpeg** with libx264, aac, drawtext and libass, plus a **Hangul font**:
  - Ubuntu/Debian: `sudo apt install ffmpeg fonts-noto-cjk`
  - macOS: `brew install ffmpeg` (Apple SD Gothic Neo is built in)
  - Windows: `winget install Gyan.FFmpeg` (Malgun Gothic is built in)
- Optional engines: see [ROUTING.md](skills/unified-video-studio/references/ROUTING.md).

## Use

Start a new session and ask in plain language:

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
S=~/.claude/skills/unified-video-studio/scripts
python3 $S/init_project.py myvideo --title "제품 소개" --duration 30   # --aspect 9:16 for Shorts
python3 $S/build.py --project myvideo --placeholders                 # animatic
python3 $S/build.py --project myvideo --burn-subs --music myvideo/assets/music.mp3 --duck
```

## What's inside

```
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
