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

say()  { printf '\033[1;34m[uvs]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[uvs] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[uvs] error:\033[0m %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: install.sh [--user|--project|--dir PATH] [--link DIR]... [--copy|--no-link]
                  [--ref REF] [--no-test] [--uninstall]
  --user       install to ~/.agents/skills/unified-video-studio (default)
  --project    install to ./.agents/skills/unified-video-studio (current repo only)
  --dir PATH   install the skill folder at PATH (no agent links unless --link)
  --link DIR   also expose the skill in DIR (an agent's skills folder); repeatable
  --copy       copy into agent folders instead of symlinking (for tools that ignore symlinks)
  --no-link    do not touch any agent folder; only the shared install
  --ref REF    branch or tag (default main, e.g. v2.1.0)
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
    local dst="$BACKUP_ROOT/$(echo "$1" | sed 's|^/||; s|/|__|g')"
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

say "checking environment (doctor.py)"
DOCTOR_OK=1
"$PY" "$DEST/scripts/doctor.py" || DOCTOR_OK=0
if [[ $DOCTOR_OK -eq 0 ]]; then
  warn "required tools are missing (see above). Typical fixes:"
  warn "  Debian/Ubuntu: sudo apt install ffmpeg fonts-noto-cjk"
  warn "  macOS:         brew install ffmpeg"
  warn "  Windows:       winget install Gyan.FFmpeg"
  warn "re-run the smoke test afterwards: $PY $DEST/tests/smoke_test.py"
elif [[ $RUN_TEST -eq 1 ]]; then
  say "running smoke test (FFmpeg only, ~20 s)"
  if "$PY" "$DEST/tests/smoke_test.py" >"$TMP/smoke.log" 2>&1; then
    say "smoke test PASS"
  else
    tail -n 30 "$TMP/smoke.log" >&2
    warn "smoke test failed; the skill is installed but check the output above"
  fi
fi

cat <<EOF

Done. Start a new agent session and ask, for example:
  "unified-video-studio로 30초 한국어 제품 홍보영상 만들어줘. 스토리보드부터 보여줘."
  "Use unified-video-studio to make a 15s vertical teaser with captions."
Agents without skill support: tell them to read $DEST/SKILL.md first.
Uninstall: curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash -s -- --uninstall
EOF
