#!/usr/bin/env bash
# Unified Video Studio (uvs) installer — agent-agnostic Agent Skill (SKILL.md format).
#
#   curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash -s -- --project
#
# The skill is installed once into the shared agent skills folder
#   user:    ~/.agents/skills/unified-video-studio
#   project: ./.agents/skills/unified-video-studio
# and symlinked into the skills folder of every agent detected on this machine
# (Claude Code: ~/.claude/skills or ./.claude/skills; Codex: ~/.codex/skills).
# Use --link DIR for any other agent. Upgrades replace the previous install in place.
set -euo pipefail

REPO="${UVS_REPO:-4mGLn/uvs}"
REF="${UVS_REF:-main}"
SKILL="unified-video-studio"
DEST="${UVS_DIR:-}"
SCOPE="user"
RUN_TEST=1
UNINSTALL=0
LINK_MODE="symlink"   # symlink | copy | none
EXTRA_LINKS=()
WITH=""               # comma list of optional tools to install (see --with)
NO_EXTRAS=0
EXTRA_NAMES="ffmpeg blender manim auto-editor whisperx edge-tts"

say()  { printf '\033[1;34m[uvs]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[uvs] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[uvs] error:\033[0m %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: install.sh [--user|--project|--dir PATH] [--link DIR]... [--copy|--no-link]
                  [--ref REF] [--with LIST|--no-extras] [--no-test] [--uninstall]
  --user       install to ~/.agents/skills/unified-video-studio (default)
  --project    install to ./.agents/skills/unified-video-studio (current repo only)
  --dir PATH   install the skill folder at PATH (no agent links unless --link)
  --link DIR   also expose the skill in DIR (an agent's skills folder); repeatable
  --copy       copy into agent folders instead of symlinking (for tools that ignore symlinks)
  --no-link    do not touch any agent folder; only the shared install
  --ref REF    branch or tag (default main, e.g. v2.2.0)
  --with LIST  also install tools, comma-separated: ffmpeg (+Hangul font), blender, manim,
               auto-editor, whisperx, edge-tts, or "all" (everything missing). Without it,
               an interactive terminal is asked per missing tool; agents/pipes are not asked.
  --no-extras  never offer to install anything beyond the skill itself
  --no-test    skip the post-install smoke test
  --uninstall  remove the install and the links/copies this installer created
Auto-detected agents: Claude Code (~/.claude: user and project), Codex ($CODEX_HOME or ~/.codex: user)
Env: UVS_REF, UVS_DIR, UVS_REPO
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user|--agents) SCOPE="user" ;;
    --project) SCOPE="project" ;;
    --dir) [[ $# -ge 2 ]] || die "--dir needs a path"; DEST="$2"; shift ;;
    --link) [[ $# -ge 2 ]] || die "--link needs a directory"; EXTRA_LINKS+=("$2"); shift ;;
    --copy) LINK_MODE="copy" ;;
    --no-link) LINK_MODE="none" ;;
    --ref) [[ $# -ge 2 ]] || die "--ref needs a value"; REF="$2"; shift ;;
    --no-test) RUN_TEST=0 ;;
    --with) [[ $# -ge 2 ]] || die "--with needs a list"; WITH="${WITH:+$WITH,}$2"; shift ;;
    --no-extras) NO_EXTRAS=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
  shift
done

if [[ "$SCOPE" == "project" ]]; then BASE="$PWD"; else BASE="$HOME"; fi
CUSTOM_DEST=0
if [[ -n "$DEST" ]]; then CUSTOM_DEST=1; else DEST="$BASE/.agents/skills/$SKILL"; fi
case "$DEST" in
  ""|"/"|"$HOME"|"$HOME/") die "refusing unsafe install path: '$DEST'" ;;
esac

# Agent skill folders to expose the skill in: detected agents + --link.
# A custom --dir never touches agent folders unless --link is given.
AGENT_DIRS=()
if [[ "$LINK_MODE" != "none" && $CUSTOM_DEST -eq 0 ]]; then
  [[ -d "$HOME/.claude" ]] && AGENT_DIRS+=("$BASE/.claude/skills")
  # Codex: user-level skills folder only (project scope relies on ./.agents/skills)
  CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
  if [[ -d "$CODEX_DIR" && "$SCOPE" == "user" ]]; then AGENT_DIRS+=("$CODEX_DIR/skills"); fi
fi
for d in "${EXTRA_LINKS[@]+"${EXTRA_LINKS[@]}"}"; do AGENT_DIRS+=("$d"); done

is_our_skill() { [[ -f "$1/SKILL.md" ]] && grep -q "^name: $SKILL" "$1/SKILL.md"; }

if [[ $UNINSTALL -eq 1 ]]; then
  removed=0
  for d in "${AGENT_DIRS[@]+"${AGENT_DIRS[@]}"}"; do
    t="$d/$SKILL"
    if [[ -L "$t" ]]; then rm "$t"; say "removed link $t"; removed=1
    elif [[ -d "$t" ]] && [[ -f "$t/.uvs-installed-copy" ]]; then rm -rf "$t"; say "removed copy $t"; removed=1
    fi
  done
  if is_our_skill "$DEST"; then rm -rf "$DEST"; say "removed $DEST"; removed=1; fi
  [[ $removed -eq 1 ]] || die "nothing to uninstall at $DEST"
  exit 0
fi

command -v tar >/dev/null || die "tar is required"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then PY="$c"; break; fi
done
[[ -n "$PY" ]] || die "Python >= 3.9 is required (the skill scripts use only the standard library)"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/uvs-install.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
STAMP="$(date +%Y%m%d%H%M%S)"

# Use a local checkout when run from one (bash install.sh), else download the archive.
SRC=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/skills/$SKILL/SKILL.md" ]]; then
  SRC="$SCRIPT_DIR/skills/$SKILL"
  say "installing from local checkout $SCRIPT_DIR"
else
  URL="https://github.com/$REPO/archive/$REF.tar.gz"
  say "downloading $REPO@$REF"
  if command -v curl >/dev/null; then
    curl -fsSL "$URL" -o "$TMP/uvs.tar.gz" || die "download failed: $URL"
  elif command -v wget >/dev/null; then
    wget -qO "$TMP/uvs.tar.gz" "$URL" || die "download failed: $URL"
  else
    die "curl or wget is required"
  fi
  tar -xzf "$TMP/uvs.tar.gz" -C "$TMP"
  SRC="$(find "$TMP" -mindepth 3 -maxdepth 3 -type d -path "*/skills/$SKILL" | head -n 1)"
  [[ -n "$SRC" && -f "$SRC/SKILL.md" ]] || die "archive does not contain skills/$SKILL"
fi

# Backups go OUTSIDE every skills folder: agents scan those folders and would load
# a "<name>.bak-*" directory as a second, duplicate skill.
BACKUP_ROOT="$BASE/.agents/.uvs-backups/$STAMP"
backup() {  # replace any previous install of this skill; move anything else out of the way
  if [[ -L "$1" ]]; then rm "$1"
  elif [[ -f "$1/.uvs-installed-copy" ]] || is_our_skill "$1"; then
    rm -rf "$1"   # an older copy of this same skill (reinstallable from git)
  elif [[ -e "$1" ]]; then
    local dst
    dst="$BACKUP_ROOT/$(echo "$1" | sed 's|^/||; s|/|__|g')"
    mkdir -p "$BACKUP_ROOT"; mv "$1" "$dst"; say "existing $1 moved to $dst"
  fi
}

mkdir -p "$(dirname "$DEST")"
backup "$DEST"
cp -R "$SRC" "$DEST"
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
chmod +x "$DEST"/scripts/*.py "$DEST"/tests/*.py 2>/dev/null || true
VERSION="$(sed -n 's/^Version \([0-9.]*\).*/\1/p' "$DEST/README.md" | head -n 1)"
say "installed $SKILL ${VERSION:+v$VERSION }to $DEST"

for d in "${AGENT_DIRS[@]+"${AGENT_DIRS[@]}"}"; do
  t="$d/$SKILL"
  [[ "$(cd "$(dirname "$t")" 2>/dev/null && pwd)/$SKILL" == "$DEST" ]] && continue
  mkdir -p "$d"
  backup "$t"
  if [[ "$LINK_MODE" == "copy" ]]; then
    cp -R "$DEST" "$t" && touch "$t/.uvs-installed-copy"
    say "copied into $t"
  else
    # relative link: survives moving the project folder / committing .claude/skills
    rel="$("$PY" -c 'import os,sys; print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))' "$DEST" "$t")"
    ln -s "$rel" "$t"
    say "linked $t -> $rel"
  fi
done
if [[ ${#AGENT_DIRS[@]} -eq 0 && "$LINK_MODE" != "none" && $CUSTOM_DEST -eq 0 ]]; then
  say "no Claude Code / Codex config found; agents that read ~/.agents/skills will find it there."
  say "for other agents: re-run with --link <their skills folder>, or point them to $DEST/SKILL.md"
fi

# ---------------------------------------------------------------- optional tools
INTERACTIVE=0
if [[ -t 1 ]] && { : </dev/tty; } 2>/dev/null; then INTERACTIVE=1; fi
ask() {  # ask "question" -> 0 on yes; only when a human is at a terminal
  [[ $INTERACTIVE -eq 1 ]] || return 1
  local ans; read -r -p "$(printf '\033[1;36m[uvs]\033[0m %s [y/N] ' "$1")" ans </dev/tty || return 1
  [[ "$ans" =~ ^[Yy] ]]
}
wanted() { [[ ",$WITH," == *",all,"* || ",$WITH," == *",$1,"* ]]; }
for w in ${WITH//,/ }; do
  [[ " $EXTRA_NAMES all " == *" $w "* ]] || die "--with: unknown tool '$w' (choose from: $EXTRA_NAMES all)"
done

OS="$(uname -s)"
PKG=""
if [[ "$OS" == "Darwin" ]] && command -v brew >/dev/null; then PKG="brew"
elif command -v apt-get >/dev/null; then PKG="apt"
fi

run_root() {  # run a command needing root: root, cached sudo, or interactive sudo; else print it
  if [[ $EUID -eq 0 ]]; then "$@"; return; fi
  if ! command -v sudo >/dev/null; then warn "needs root; run manually: $*"; return 1; fi
  if sudo -n true 2>/dev/null; then sudo "$@"; return; fi
  if [[ $INTERACTIVE -eq 1 ]]; then sudo "$@" </dev/tty; return; fi
  warn "needs sudo (no terminal to ask for a password); run manually: sudo $*"
  return 1
}
uv_tool() {  # uv tool install <pkg>
  if ! command -v uv >/dev/null; then
    warn "uv is required for $1: curl -LsSf https://astral.sh/uv/install.sh | sh  (then re-run)"
    return 1
  fi
  uv tool install --quiet "$1" || uv tool upgrade --quiet "$1"
  local bin; bin="$(uv tool dir --bin 2>/dev/null || true)"
  if [[ -n "$bin" && ":$PATH:" != *":$bin:"* ]]; then
    warn "$bin is not on PATH; run 'uv tool update-shell' and open a new shell"
    export PATH="$bin:$PATH"
  fi
}

have() {
  case "$1" in
    ffmpeg) command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null && { ! command -v fc-list >/dev/null || [[ -n "$(fc-list :lang=ko 2>/dev/null | head -n 1)" ]]; } ;;
    edge-tts) command -v edge-tts >/dev/null || command -v uvx >/dev/null ;;  # tts.py falls back to uvx
    *) command -v "$1" >/dev/null ;;
  esac
}
describe() {
  case "$1" in
    ffmpeg) echo "FFmpeg + Hangul font (required, ~100 MB, needs sudo on Linux)" ;;
    blender) echo "Blender 3D (~300 MB+, needs sudo on Linux)" ;;
    manim) echo "Manim math animation (~150 MB via uv; Linux needs cairo/pango dev libs via sudo)" ;;
    auto-editor) echo "Auto-Editor silence cutting (~50 MB via uv)" ;;
    whisperx) echo "WhisperX transcription (several GB incl. PyTorch; slow without a big GPU)" ;;
    edge-tts) echo "edge-tts online TTS (small, via uv)" ;;
  esac
}
install_tool() {
  say "installing $1"
  case "$1" in
    ffmpeg)
      case "$PKG" in
        apt) run_root apt-get update -qq && run_root apt-get install -y ffmpeg fonts-noto-cjk ;;
        brew) brew install ffmpeg ;;
        *) warn "install FFmpeg manually (https://ffmpeg.org/download.html) and a Hangul font"; return 1 ;;
      esac ;;
    blender)
      case "$PKG" in
        apt) run_root apt-get install -y blender ;;
        brew) brew install --cask blender ;;
        *) warn "download Blender from https://www.blender.org/download/"; return 1 ;;
      esac ;;
    manim)
      case "$PKG" in
        apt) run_root apt-get install -y libcairo2-dev libpango1.0-dev pkg-config python3-dev || return 1 ;;
        brew) brew install cairo pango pkg-config || return 1 ;;
      esac
      uv_tool manim
      say "manim: formulas (MathTex) also need LaTeX, e.g. 'sudo apt install texlive-latex-extra' (not installed automatically)" ;;
    auto-editor) uv_tool auto-editor ;;
    whisperx) uv_tool whisperx ;;
    edge-tts) uv_tool edge-tts ;;
  esac
}

offer_tools() {  # $@ = candidate names; installs per --with / interactive answer
  local missing=() t
  for t in "$@"; do have "$t" || missing+=("$t"); done
  [[ ${#missing[@]} -gt 0 ]] || return 0
  local chosen=()
  for t in "${missing[@]}"; do
    if [[ -n "$WITH" ]]; then wanted "$t" && chosen+=("$t")
    elif ask "install $(describe "$t")?"; then chosen+=("$t")
    fi
  done
  if [[ ${#chosen[@]} -eq 0 ]]; then
    if [[ -z "$WITH" && $INTERACTIVE -eq 0 ]]; then
      say "not installed: ${missing[*]} (optional unless listed as required)."
      say "  to install: re-run the installer with --with $(IFS=,; echo "${missing[*]}")  (or --with all)"
    fi
    return 0
  fi
  INSTALLED_SOMETHING=1
  for t in "${chosen[@]}"; do
    if install_tool "$t" && have "$t"; then say "$t: ready"; else warn "$t: not installed (see messages above)"; fi
  done
}

INSTALLED_SOMETHING=0
say "checking environment (doctor.py)"
DOCTOR_OK=1
"$PY" "$DEST/scripts/doctor.py" >"$TMP/doctor.txt" 2>&1 || DOCTOR_OK=0
cat "$TMP/doctor.txt"
if [[ $DOCTOR_OK -eq 0 && $NO_EXTRAS -eq 0 ]]; then
  offer_tools ffmpeg
  if [[ $INSTALLED_SOMETHING -eq 1 ]]; then
    DOCTOR_OK=1; "$PY" "$DEST/scripts/doctor.py" >/dev/null 2>&1 || DOCTOR_OK=0
  fi
fi
if [[ $DOCTOR_OK -eq 0 ]]; then
  warn "required tools are missing (see above). Typical fixes:"
  warn "  Debian/Ubuntu: sudo apt install ffmpeg fonts-noto-cjk   (or: bash install.sh --with ffmpeg)"
  warn "  macOS:         brew install ffmpeg"
  warn "  Windows:       winget install Gyan.FFmpeg"
  warn "re-run the smoke test afterwards: $PY $DEST/tests/smoke_test.py"
else
  if [[ $NO_EXTRAS -eq 0 ]]; then
    before=$INSTALLED_SOMETHING
    offer_tools blender manim auto-editor whisperx edge-tts
    if grep -q "comfyui" "$TMP/doctor.txt" && ! grep -q "\[ready\] comfyui" "$TMP/doctor.txt"; then
      say "comfyui is never installed automatically (large; needs a GPU with >= 8 GB VRAM). See references/engines/comfyui.md"
    fi
    if [[ $INSTALLED_SOMETHING -ne $before ]]; then
      say "environment after installing tools:"
      "$PY" "$DEST/scripts/doctor.py" | sed -n '/== engines ==/,/== gpu ==/p' | sed '$d'
    fi
  fi
  if [[ $RUN_TEST -eq 1 ]]; then
    say "running smoke test (FFmpeg only, ~20 s)"
    if "$PY" "$DEST/tests/smoke_test.py" >"$TMP/smoke.log" 2>&1; then
      say "smoke test PASS"
    else
      tail -n 30 "$TMP/smoke.log" >&2
      warn "smoke test failed; the skill is installed but check the output above"
    fi
  fi
fi

cat <<EOF

Done. Start a new agent session and ask, for example:
  "unified-video-studio로 30초 한국어 제품 홍보영상 만들어줘. 스토리보드부터 보여줘."
  "Use unified-video-studio to make a 15s vertical teaser with captions."
Agents without skill support: tell them to read $DEST/SKILL.md first.
Uninstall: curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash -s -- --uninstall
EOF
