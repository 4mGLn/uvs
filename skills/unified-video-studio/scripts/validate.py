#!/usr/bin/env python3
"""Validate a project's brief.json and storyboard.json before rendering.

Checks: schema/types, unique shot ids, timeline continuity, engine/transition
values, total duration vs brief, voiceover speed, on-screen text length,
asset provenance, and (with --check-clips) rendered clip presence/duration.

Usage:
  validate.py --project project/ [--check-clips] [--strict]
  validate.py --brief b.json --storyboard s.json
Exit code 0 = no errors (warnings allowed unless --strict), 1 = errors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import (ENGINES, TRANSITIONS, UVSError, clip_path_for, ffprobe,  # noqa: E402
                        fps_value, load_json, shots_of, video_duration)

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
COLOR_RE = re.compile(r"^(#|0x)?[0-9A-Fa-f]{6}$|^[a-zA-Z]+$")
# Korean narration is roughly 4-6 syllables/second; above ~7 it sounds rushed.
MAX_VO_CPS = {"ko": 7.0, "ja": 8.0, "zh": 5.5}
DEFAULT_VO_WPS = 3.0  # words/second for space-separated languages


def spoken_rate(text: str, lang: str, seconds: float) -> tuple[float, float, str]:
    if lang in MAX_VO_CPS:
        n = len(re.sub(r"[\s\W_]", "", text))
        return n / seconds, MAX_VO_CPS[lang], "chars/s"
    n = len(text.split())
    return n / seconds, DEFAULT_VO_WPS, "words/s"


def validate(brief: dict, sb: dict, project: Path | None, check_clips: bool) -> tuple[list, list]:
    errors: list[str] = []
    warns: list[str] = []

    def need(obj: dict, key: str, types, where: str, required: bool = True):
        if key not in obj:
            if required:
                errors.append(f"{where}: missing '{key}'")
            return None
        val = obj[key]
        allowed = types if isinstance(types, tuple) else (types,)
        if not isinstance(val, allowed) or (isinstance(val, bool) and bool not in allowed):
            errors.append(f"{where}: '{key}' has wrong type ({type(obj[key]).__name__})")
            return None
        return obj[key]

    # ---- brief
    w = need(brief, "width", int, "brief")
    h = need(brief, "height", int, "brief")
    fps = need(brief, "fps", (int, float), "brief")
    dur = need(brief, "duration_s", (int, float), "brief")
    lang = need(brief, "language", str, "brief") or "ko"
    need(brief, "title", str, "brief")
    need(brief, "goal", str, "brief", required=False)
    for name, val in (("width", w), ("height", h)):
        if val is not None and (val < 16 or val > 8192 or val % 2):
            errors.append(f"brief: {name} must be an even number between 16 and 8192 (H.264/yuv420p)")
    if fps is not None and not (1 <= fps <= 120):
        errors.append("brief: fps out of range 1-120")
    if dur is not None and dur <= 0:
        errors.append("brief: duration_s must be > 0")
    for k in ("assets", "rights_notes"):
        if k in brief and not isinstance(brief[k], list):
            errors.append(f"brief: '{k}' must be a list")

    # ---- storyboard
    try:
        shots = shots_of(sb)
    except UVSError as e:
        errors.append(str(e))
        return errors, warns
    seen: set[str] = set()
    cursor = 0.0
    prev_fade_half = 0.0  # fade-in this shot inherits from the previous shot's fade transition
    fv = fps_value(fps) if isinstance(fps, (int, float)) and fps > 0 else None
    for i, s in enumerate(shots):
        where = f"shot[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{where}: must be an object")
            continue
        sid = need(s, "id", str, where)
        if sid:
            where = f"shot '{sid}'"
            if not ID_RE.match(sid):
                errors.append(f"{where}: id must match {ID_RE.pattern} (used as a file name)")
            if sid in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(sid)
        d = need(s, "duration_s", (int, float), where)
        if d is not None and d <= 0:
            errors.append(f"{where}: duration_s must be > 0")
            d = None
        st = s.get("start_s")
        if st is not None:
            if not isinstance(st, (int, float)):
                errors.append(f"{where}: start_s must be a number")
            elif abs(st - cursor) > 0.05:
                kind = "overlaps previous shot" if st < cursor else "leaves a gap after previous shot"
                errors.append(f"{where}: start_s={st} but expected {cursor:.2f} ({kind}); "
                              "shots are laid end-to-end — fix start_s or omit it")
        eng = need(s, "engine", str, where)
        if eng and eng not in ENGINES:
            errors.append(f"{where}: unknown engine '{eng}' (allowed: {', '.join(sorted(ENGINES))})")
        tr = s.get("transition", "cut")
        if tr not in TRANSITIONS:
            errors.append(f"{where}: transition '{tr}' not in {sorted(TRANSITIONS)}")
        ts = s.get("transition_s", 0.6)
        is_last = i == len(shots) - 1
        fade_out = 0.0
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or ts < 0:
            errors.append(f"{where}: transition_s must be a number >= 0")
        elif tr == "fade":
            fade_out = ts if is_last else ts / 2
        if d and prev_fade_half + fade_out > d + 1e-6:
            errors.append(f"{where}: fades need {prev_fade_half + fade_out:.2f}s (in {prev_fade_half:.2f}s from previous "
                          f"shot + out {fade_out:.2f}s) but the shot is {d}s; shorten transition_s or lengthen the shot")
        prev_fade_half = ts / 2 if (tr == "fade" and isinstance(ts, (int, float))) else 0.0
        if d and fv and abs(d * fv - round(d * fv)) > 0.01:
            warns.append(f"{where}: {d}s is not a whole number of frames at {fps}fps "
                         f"({d * fv:.2f}); timing is rounded to frames")
        for key in ("on_screen_text", "voiceover", "visual_direction", "purpose"):
            if key in s and not isinstance(s[key], str):
                errors.append(f"{where}: '{key}' must be a string")
        vo_off = s.get("voiceover_offset_s")
        if vo_off is not None and (not isinstance(vo_off, (int, float)) or isinstance(vo_off, bool) or vo_off < 0):
            errors.append(f"{where}: voiceover_offset_s must be a number >= 0")
        if "assets" in s and not isinstance(s["assets"], list):
            errors.append(f"{where}: 'assets' must be a list")
        for key in ("clip", "voiceover_audio"):
            if key in s:
                if not isinstance(s[key], str) or not s[key]:
                    errors.append(f"{where}: '{key}' must be a non-empty path string")
                elif project:
                    fp = Path(s[key])
                    fp = fp if fp.is_absolute() else project / fp
                    if not fp.is_file() and not (key == "clip" and eng != "footage"):
                        errors.append(f"{where}: {key} not found: {fp}")
        if eng == "footage" and not s.get("clip"):
            errors.append(f"{where}: engine 'footage' needs a 'clip' path")
        if eng == "image":
            assets = s.get("assets") if isinstance(s.get("assets"), list) else []
            imgs = [a for a in assets if isinstance(a, dict) and a.get("type") == "image"]
            if not imgs:
                errors.append(f"{where}: engine 'image' needs an asset with type 'image'")
            elif project:
                for a in imgs:
                    p = Path(str(a.get("path") or ""))
                    p = p if p.is_absolute() else project / p
                    if not a.get("path") or not p.is_file():
                        errors.append(f"{where}: image asset not found: {p}")
        style = s.get("style", {})
        if style is None:
            style = {}
        if not isinstance(style, dict):
            errors.append(f"{where}: style must be an object")
        else:
            for ck in ("bg", "fg", "accent"):
                if ck in style and not (isinstance(style[ck], str) and COLOR_RE.match(style[ck])):
                    errors.append(f"{where}: style.{ck} must be a color like '#112233'")
            fs = style.get("font_size")
            if fs is not None and (not isinstance(fs, (int, float)) or isinstance(fs, bool) or not 8 <= fs <= 400):
                errors.append(f"{where}: style.font_size must be a number 8-400 (px at 1080p)")
            if style.get("align", "center") not in ("center", "left"):
                errors.append(f"{where}: style.align must be 'center' or 'left'")
            if style.get("motion", "zoom") not in ("zoom", "none"):
                errors.append(f"{where}: style.motion must be 'zoom' or 'none'")
            if "subtitle" in style and not isinstance(style["subtitle"], str):
                errors.append(f"{where}: style.subtitle must be a string")
        text = s.get("on_screen_text", "")
        if isinstance(text, str) and text:
            longest = max(len(x) for x in text.splitlines())
            if longest > (24 if lang in MAX_VO_CPS else 45):
                warns.append(f"{where}: on_screen_text line is long ({longest} chars); hard to read in a {d or '?'}s shot")
        vo = s.get("voiceover", "")
        if isinstance(vo, str) and vo.strip() and d:
            rate, limit, unit = spoken_rate(vo, lang, d)
            if rate > limit:
                warns.append(f"{where}: voiceover too fast ({rate:.1f} {unit} > {limit}); shorten text or lengthen shot")
        for j, a in enumerate(s.get("assets") if isinstance(s.get("assets"), list) else []):
            if not isinstance(a, dict):
                errors.append(f"{where}: assets[{j}] must be an object with path/source/license")
                continue
            missing = [k for k in ("source", "license") if not a.get(k)]
            if missing:
                warns.append(f"{where}: asset '{a.get('path', j)}' lacks {', '.join(missing)} (provenance)")
        if check_clips and project and sid and eng:
            cp = clip_path_for(s, project)
            if not cp.is_file():
                errors.append(f"{where}: rendered clip missing: {cp}")
            elif d:
                cd = video_duration(ffprobe(cp))
                if cd + 0.05 < d:
                    warns.append(f"{where}: clip is {cd:.2f}s, shorter than {d}s (last frame will be held)")
                elif cd > d + 0.5:
                    warns.append(f"{where}: clip is {cd:.2f}s, longer than {d}s (will be trimmed)")
        if d:
            cursor += d

    if dur and abs(cursor - dur) > max(0.5, 0.05 * dur):
        warns.append(f"storyboard total {cursor:.2f}s differs from brief duration_s {dur}s")
    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="project directory containing brief.json and storyboard.json")
    ap.add_argument("--brief")
    ap.add_argument("--storyboard")
    ap.add_argument("--check-clips", action="store_true", help="require rendered clips to exist")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    a = ap.parse_args()
    try:
        project = Path(a.project).resolve() if a.project else None
        bp = Path(a.brief) if a.brief else (project / "brief.json" if project else None)
        sp = Path(a.storyboard) if a.storyboard else (project / "storyboard.json" if project else None)
        if not bp or not sp:
            ap.error("give --project or both --brief and --storyboard")
        if project is None:
            project = sp.resolve().parent
        errors, warns = validate(load_json(bp), load_json(sp), project, a.check_clips)
    except UVSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    failed = bool(errors) or (a.strict and bool(warns))
    print(json.dumps({"passed": not failed, "errors": errors, "warnings": warns}, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
