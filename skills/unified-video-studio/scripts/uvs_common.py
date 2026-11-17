"""Shared helpers for unified-video-studio scripts (stdlib only)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ENGINES = {
    "ffmpeg-title",  # built-in title/text card rendered by render_builtin.py
    "image",         # still image turned into a clip by render_builtin.py
    "footage",       # existing video file supplied as shot "clip"
    "hyperframes",
    "remotion",
    "blender",
    "manim",
    "comfyui",
}
BUILTIN_ENGINES = {"ffmpeg-title", "image"}
TRANSITIONS = {"cut", "fade"}

KO_FONT_CANDIDATES = [
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "NanumGothic",
    "Nanum Gothic",
    "Malgun Gothic",
    "Apple SD Gothic Neo",
    "UnDotum",
]


class UVSError(Exception):
    """User-facing error; scripts print it without a traceback."""


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def require_tools(*names: str) -> None:
    missing = [n for n in names if shutil.which(n) is None]
    if missing:
        raise UVSError(
            f"required tool(s) not found on PATH: {', '.join(missing)}. "
            "Install FFmpeg (e.g. `sudo apt install ffmpeg`, `brew install ffmpeg`) "
            "and run scripts/doctor.py."
        )


def ffprobe(path: str | Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise UVSError(f"ffprobe could not read {path}: {proc.stderr.strip()[-300:]}")
    data = json.loads(proc.stdout or "{}")
    data.setdefault("streams", [])
    data.setdefault("format", {})
    return data


def stream(info: dict, kind: str) -> dict | None:
    return next((s for s in info["streams"] if s.get("codec_type") == kind), None)


def duration_of(info: dict) -> float:
    try:
        return float(info["format"].get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "N/A"):
        return None
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else None
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def load_json(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise UVSError(f"file not found: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise UVSError(f"invalid JSON in {p}: {e}") from e


def find_korean_font() -> tuple[str, str] | None:
    """Return (font_file, family_name) for a Hangul-capable font, or None.

    family_name is the name libass/fontconfig can resolve (used in subtitle styles).
    """
    if shutil.which("fc-match"):
        for fam in KO_FONT_CANDIDATES:
            proc = subprocess.run(
                ["fc-match", "-f", "%{family}|%{file}", f"{fam}:lang=ko"],
                capture_output=True, text=True,
            )
            out = proc.stdout.strip()
            if proc.returncode == 0 and "|" in out:
                families, file = out.rsplit("|", 1)
                norm = fam.lower().replace(" ", "")
                if any(norm == f.lower().replace(" ", "") for f in families.split(",")) and Path(file).is_file():
                    return file, fam
    if shutil.which("fc-list"):
        proc = subprocess.run(["fc-list", ":lang=ko", "file", "family"], capture_output=True, text=True)
        for line in sorted(proc.stdout.splitlines()):
            file, _, fams = line.partition(":")
            file = file.strip()
            if file and Path(file).is_file():
                return file, (fams.split(",")[0].strip() or "sans-serif")
    for cand, fam in (
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "Apple SD Gothic Neo"),
        ("C:/Windows/Fonts/malgun.ttf", "Malgun Gothic"),
    ):
        if Path(cand).is_file():
            return cand, fam
    return None


def shots_of(storyboard: dict) -> list[dict]:
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or not shots:
        raise UVSError("storyboard has no 'shots' list")
    return shots


def clip_path_for(shot: dict, project: Path) -> Path:
    """Where a shot's rendered clip lives: explicit 'clip' or renders/clips/<id>.mp4."""
    if shot.get("clip"):
        p = Path(shot["clip"])
        return p if p.is_absolute() else (project / p)
    return project / "renders" / "clips" / f"{shot['id']}.mp4"


def placeholder_path_for(shot: dict, project: Path) -> Path:
    return project / "renders" / "placeholders" / f"{shot['id']}.mp4"


def resolve_clip(shot: dict, project: Path, allow_placeholder: bool) -> tuple[Path | None, bool]:
    """Return (path, is_placeholder). Real clips always win over placeholders."""
    real = clip_path_for(shot, project)
    if real.is_file():
        return real, False
    ph = placeholder_path_for(shot, project)
    if allow_placeholder and ph.is_file():
        return ph, True
    return None, False


NTSC_RATES = {29.97: "30000/1001", 23.976: "24000/1001", 59.94: "60000/1001", 47.952: "48000/1001"}


def fps_rate(fps: float) -> str:
    """ffmpeg rate string; NTSC-style decimals map to exact x/1001 rationals."""
    for approx, exact in NTSC_RATES.items():
        if abs(float(fps) - approx) < 0.005:
            return exact
    f = float(fps)
    return str(int(f)) if f.is_integer() else f"{f:.6g}"


def fps_value(fps: float) -> float:
    r = fps_rate(fps)
    if "/" in r:
        n, d = r.split("/")
        return int(n) / int(d)
    return float(r)


def video_duration(info: dict) -> float:
    """Duration of the video stream (format duration may be the longer audio)."""
    v = stream(info, "video")
    if v:
        try:
            d = float(v.get("duration") or 0)
            if d > 0:
                return d
        except (TypeError, ValueError):
            pass
        nb, rate = v.get("nb_frames"), parse_rate(v.get("avg_frame_rate"))
        if nb and str(nb).isdigit() and rate:
            return int(nb) / rate
    return duration_of(info)


def display_size(v: dict) -> tuple[int, int]:
    """Width/height after applying rotation metadata (ffmpeg autorotates)."""
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rot = int(float(sd["rotation"]))
            except (TypeError, ValueError):
                pass
    if not rot:
        try:
            rot = int((v.get("tags") or {}).get("rotate", 0))
        except (TypeError, ValueError):
            rot = 0
    return (h, w) if abs(rot) % 180 == 90 else (w, h)


def shot_frame_bounds(shots: list[dict], fps: float) -> list[tuple[int, int]]:
    """Frame-exact [start, end) per shot from cumulative time, so rounding never drifts."""
    f = fps_value(fps)
    out, t = [], 0.0
    for s in shots:
        start = round(t * f)
        t += float(s["duration_s"])
        out.append((start, round(t * f)))
    return out


def voice_offset_of(shot: dict) -> float:
    """Seconds after shot start where the voiceover begins (default 0.15)."""
    v = shot.get("voiceover_offset_s")
    return 0.15 if v is None else float(v)
