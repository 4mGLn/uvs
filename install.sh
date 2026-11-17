#!/usr/bin/env bash
# Unified Video Studio (uvs) installer for Claude Code / agent skills.
#
#   curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/4mGLn/uvs/main/install.sh | bash -s -- --project
#
# Options:
#   --user            install to ~/.claude/skills/unified-video-studio (default)
#   --project         install to ./.claude/skills/unified-video-studio (current repo only)
#   --agents          install to ~/.agents/skills/unified-video-studio (other agent CLIs)
#   --dir PATH        install to PATH (the skill folder itself)
#   --ref REF         branch or tag to install (default: main; e.g. v2.0.0)
#   --no-test         skip the post-install smoke test
#   --uninstall       remove the skill from the chosen location
#   -h, --help        show this help
# Environment: UVS_REF, UVS_DIR, UVS_REPO (default 4mGLn/uvs)
set -euo pipefail

REPO="${UVS_REPO:-4mGLn/uvs}"
REF="${UVS_REF:-main}"
SKILL="unified-video-studio"
DEST="${UVS_DIR:-}"
SCOPE="user"
RUN_TEST=1
UNINSTALL=0

say()  { printf '\033[1;34m[uvs]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[uvs] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[uvs] error:\033[0m %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: install.sh [--user|--project|--agents|--dir PATH] [--ref REF] [--no-test] [--uninstall]
  --user       ~/.claude/skills/unified-video-studio (default)
  --project    ./.claude/skills/unified-video-studio (current repo only)
  --agents     ~/.agents/skills/unified-video-studio (other agent CLIs)
  --dir PATH   custom skill folder
  --ref REF    branch or tag (default main, e.g. v2.0.0)
  --no-test    skip the post-install smoke test
  --uninstall  remove the skill from the chosen location
Env: UVS_REF, UVS_DIR, UVS_REPO
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) SCOPE="user" ;;
    --project) SCOPE="project" ;;
    --agents) SCOPE="agents" ;;
    --dir) [[ $# -ge 2 ]] || die "--dir needs a path"; DEST="$2"; shift ;;
    --ref) [[ $# -ge 2 ]] || die "--ref needs a value"; REF="$2"; shift ;;
    --no-test) RUN_TEST=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
  shift
done

if [[ -z "$DEST" ]]; then
  case "$SCOPE" in
    user)    DEST="$HOME/.claude/skills/$SKILL" ;;
    project) DEST="$PWD/.claude/skills/$SKILL" ;;
    agents)  DEST="$HOME/.agents/skills/$SKILL" ;;
  esac
fi
case "$DEST" in
  ""|"/"|"$HOME"|"$HOME/") die "refusing unsafe install path: '$DEST'" ;;
esac

if [[ $UNINSTALL -eq 1 ]]; then
  if [[ -f "$DEST/SKILL.md" ]] && grep -q "^name: $SKILL" "$DEST/SKILL.md"; then
    rm -rf "$DEST"
    say "removed $DEST"
  else
    die "no $SKILL skill found at $DEST"
  fi
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

# Use a local checkout when the script is run from one (bash install.sh), else download.
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

mkdir -p "$(dirname "$DEST")"
if [[ -e "$DEST" ]]; then
  BACKUP="$DEST.bak-$(date +%Y%m%d%H%M%S)"
  mv "$DEST" "$BACKUP"
  say "existing install moved to $BACKUP"
fi
cp -R "$SRC" "$DEST"
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
chmod +x "$DEST"/scripts/*.py "$DEST"/tests/*.py 2>/dev/null || true
VERSION="$(sed -n 's/^Version \([0-9.]*\).*/\1/p' "$DEST/README.md" | head -n 1)"
say "installed $SKILL ${VERSION:+v$VERSION }to $DEST"

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

Done. Start a new Claude Code session and ask, for example:
  "unified-video-studio로 30초 한국어 제품 홍보영상 만들어줘. 스토리보드부터 보여줘."
  "Use unified-video-studio to make a 15s vertical teaser with captions."
Uninstall: curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash -s -- --uninstall
EOF
