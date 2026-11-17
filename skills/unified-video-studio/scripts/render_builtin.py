#!/usr/bin/env python3
"""Render storyboard shots that need only FFmpeg into project/renders/clips/<id>.mp4.

  engine "ffmpeg-title" : solid background + Korean-safe text card (fade-in)
  engine "image"        : still image (cover-fit, optional slow zoom) + optional lower-third text
  --placeholders        : any other shot whose clip is missing gets a labeled grey card in
                          renders/placeholders/, so the whole video can be previewed as an
                          animatic (assemble.py --allow-placeholders); real clips always win

Shot "style" keys (all optional): bg, fg, accent (#RRGGBB), font_size (px at 1080p),
subtitle (smaller second text), align (center|left), motion (none|zoom, image only).

Usage: render_builtin.py --project project/ [--only shot-001,shot-002] [--placeholders] [--force]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import (BUILTIN_ENGINES, UVSError, clip_path_for, find_korean_font,  # noqa: E402
                        fps_rate, fps_value, load_json, placeholder_path_for, require_tools, shots_of)


def color(c: str | None, default: str) -> str:
    c = (c or default).strip()
    if c.startswith("#"):
        return "0x" + c[1:]
    return c


def char_w(ch: str) -> float:
    """Approximate advance width in em units."""
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    if ch == " ":
        return 0.3
    return 0.58


def wrap(text: str, font_px: int, max_px: int) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        cur, cur_w = "", 0.0
        for word in para.split(" "):
            ww = sum(char_w(c) for c in word) * font_px
            sp = char_w(" ") * font_px if cur else 0
            if cur and cur_w + sp + ww > max_px:
                lines.append(cur)
                cur, cur_w = "", 0.0
                sp = 0
            if ww > max_px:  # very long word / no spaces: break by character
                for ch in word:
                    cw = char_w(ch) * font_px
                    if cur_w + cw > max_px and cur:
                        lines.append(cur)
                        cur, cur_w = "", 0.0
                    cur += ch
                    cur_w += cw
                continue
            cur += (" " if cur else "") + word
            cur_w += sp + ww
        lines.append(cur)
    return lines


def text_filters(lines: list[str], workdir: Path, prefix: str, *, font: str, size: int, fg: str,
                 y_top: str, line_h: int, align: str, margin: int, fade: float, start: float = 0.0) -> list[str]:
    """One drawtext per line (true per-line centering). Text goes through files (no filtergraph
    escaping) and expansion=none so %, { and backslashes render literally."""
    out = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        tf = f"{prefix}_{i}.txt"
        (workdir / tf).write_text(line, encoding="utf-8")
        x = "(w-text_w)/2" if align == "center" else str(margin)
        alpha = f"if(lt(t,{start}),0,if(lt(t,{start + fade}),(t-{start})/{fade},1))" if fade > 0 else "1"
        out.append(
            f"drawtext=fontfile=font.bin:textfile={tf}:expansion=none:fontsize={size}:fontcolor={fg}:"
            f"x={x}:y={y_top}+{i * line_h}:alpha='{alpha}':"
            "shadowcolor=black@0.35:shadowx=2:shadowy=2"
        )
    return out


def render_shot(shot: dict, brief: dict, project: Path, out: Path, font_file: str, placeholder: bool) -> None:
    W, H = int(brief["width"]), int(brief["height"])
    fps = fps_rate(brief["fps"])
    n_frames = max(1, round(float(shot["duration_s"]) * fps_value(brief["fps"])))
    dur = float(shot["duration_s"])
    style = shot.get("style", {}) or {}
    scale = H / 1080 if W >= H else W / 1080
    engine = shot.get("engine")
    margin = int(0.08 * W)
    with tempfile.TemporaryDirectory() as tdir:
        td = Path(tdir)
        shutil.copyfile(font_file, td / "font.bin")
        filters: list[str] = []
        inputs: list[str] = []
        if engine == "image" and not placeholder:
            img = next(a for a in shot["assets"] if isinstance(a, dict) and a.get("type") == "image")
            ip = Path(img["path"])
            ip = ip if ip.is_absolute() else project / ip
            inputs = ["-loop", "1", "-framerate", str(fps), "-i", str(ip)]
            frames = n_frames
            if style.get("motion", "zoom") == "zoom":
                filters.append(f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2}")
                filters.append(f"zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")
            else:
                filters.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
            text = shot.get("on_screen_text", "")
            if text:
                size = int(style.get("font_size", 56) * scale)
                lh = int(size * 1.3)
                lines = wrap(text, size, W - 2 * margin)
                band_h = lh * len(lines) + int(size * 0.8)
                # keep the lower third above the bottom ~20% reserved for burned-in captions
                bottom = int(0.20 * H)
                filters.append(f"drawbox=x=0:y=ih-{band_h + bottom}:w=iw:h={band_h}:color=black@0.45:t=fill")
                filters += text_filters(lines, td, "lt", font="font.bin", size=size, fg=color(style.get("fg"), "#FFFFFF"),
                                        y_top=f"h-{band_h + bottom - int(size * 0.4)}", line_h=lh,
                                        align=style.get("align", "left"), margin=margin, fade=0.4)
        else:
            if placeholder:
                bg, fg = "0x3A3A3A", "0xFFFFFF"
                main = shot.get("on_screen_text") or shot.get("purpose") or shot["id"]
                sub = f"[{engine}] {shot['id']} - {shot.get('visual_direction', '')}".strip(" -")
                size = int(72 * scale)
            else:
                bg, fg = color(style.get("bg"), "#101820"), color(style.get("fg"), "#FFFFFF")
                main = shot.get("on_screen_text", "")
                sub = style.get("subtitle", "")
                size = int(style.get("font_size", 96) * scale)
            inputs = ["-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:r={fps}:d={dur}"]
            align = style.get("align", "center")
            while True:  # shrink until the block fits in 55% of the height (keeps the caption zone clear)
                lh = int(size * 1.3)
                lines = wrap(main, size, W - 2 * margin)
                sub_size = int(size * 0.42) if placeholder else int(size * 0.45)
                sub_lh = int(sub_size * 1.4)
                sub_lines = wrap(sub, sub_size, W - 2 * margin) if sub else []
                gap = int(size * 0.5) if sub_lines else 0
                total = lh * len(lines) + gap + sub_lh * len(sub_lines)
                if total <= 0.55 * H or size <= 16:
                    break
                size = int(size * 0.9)
            top = f"(h*0.9-{total})/2"  # optical center slightly above middle, away from captions
            accent = style.get("accent")
            if accent and not placeholder:
                filters.append(f"drawbox=x={'(iw-' + str(int(size * 1.5)) + ')/2' if align == 'center' else margin}:"
                               f"y=(ih*0.9-{total})/2-{int(size * 0.6)}:w={int(size * 1.5)}:h={max(4, int(size * 0.08))}:"
                               f"color={color(accent, '#FFFFFF')}:t=fill")
            filters += text_filters(lines, td, "main", font="font.bin", size=size, fg=fg, y_top=top, line_h=lh,
                                    align=align, margin=margin, fade=0.0 if placeholder else 0.5)
            if sub_lines:
                filters += text_filters(sub_lines, td, "sub", font="font.bin", size=sub_size, fg=fg + "@0.8",
                                        y_top=f"{top}+{lh * len(lines) + gap}", line_h=sub_lh, align=align,
                                        margin=margin, fade=0.0 if placeholder else 0.5, start=0.0 if placeholder else 0.3)
        filters += ["setsar=1", "format=yuv420p"]
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = td / "out.mp4"
        cmd = ["ffmpeg", "-v", "error", "-y", *inputs,
               "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
               "-filter_complex", f"[0:v]{','.join(filters)}[v]",
               "-map", "[v]", "-map", "1:a", "-frames:v", str(n_frames), "-t", f"{n_frames / fps_value(brief['fps']):.6f}", "-r", fps,
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(tmp_out)]
        # cwd=td so font.bin / *.txt resolve without filtergraph path escaping
        proc = subprocess.run(cmd, cwd=td, capture_output=True, text=True)
        if proc.returncode != 0:
            raise UVSError(f"ffmpeg failed for shot {shot['id']}:\n{proc.stderr.strip()[-1500:]}")
        shutil.move(str(tmp_out), out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--only", help="comma-separated shot ids")
    ap.add_argument("--placeholders", action="store_true", help="render labeled cards for non-built-in shots without clips")
    ap.add_argument("--force", action="store_true", help="re-render even if the clip exists")
    ap.add_argument("--font", help="font file to use (default: auto-detect a Hangul font)")
    a = ap.parse_args()
    try:
        require_tools("ffmpeg", "ffprobe")
        project = Path(a.project).resolve()
        brief = load_json(project / "brief.json")
        shots = shots_of(load_json(project / "storyboard.json"))
        font = a.font
        if not font:
            found = find_korean_font()
            if not found:
                raise UVSError("no Hangul-capable font found; install fonts-noto-cjk / fonts-nanum or pass --font")
            font = found[0]
        if not Path(font).is_file():
            raise UVSError(f"font not found: {font}")
        only = set(a.only.split(",")) if a.only else None
        done = 0
        for shot in shots:
            if only and shot["id"] not in only:
                continue
            eng = shot.get("engine")
            placeholder = eng not in BUILTIN_ENGINES
            if placeholder:
                if not a.placeholders or clip_path_for(shot, project).is_file():
                    continue
                out = placeholder_path_for(shot, project)
            else:
                out = clip_path_for(shot, project)
            if out.is_file() and not a.force:
                print(f"skip  {shot['id']} (exists; --force to re-render)")
                continue
            render_shot(shot, brief, project, out, font, placeholder)
            done += 1
            print(f"{'placeholder' if placeholder else 'render'} {shot['id']} -> {out}")
        print(f"rendered {done} clip(s)")
    except UVSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
