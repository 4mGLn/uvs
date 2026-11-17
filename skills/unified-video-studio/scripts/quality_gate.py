#!/usr/bin/env python3
"""Technical QA for a rendered video, with a JSON report and review frames.

Errors (fail): missing streams, resolution/fps/duration mismatch, non-yuv420p,
true peak above --max-peak, unreadable file, caption cues outside the video.
Warnings: black segments, long silence, silent track, loudness off target,
frozen video (--freeze), caption reading speed / line length / overlaps.

Frames: --frames-dir writes evenly spaced frames + contact_sheet.jpg; with a
storyboard, one mid-shot frame per shot (<shot-id>.jpg). Look at them — FFmpeg
cannot judge caption safe zones, typos or brand correctness.

Usage:
  quality_gate.py --project project/ [video]       # expectations from brief/storyboard,
                                                   # report+frames in project/qa/
  quality_gate.py final.mp4 --width 1920 --height 1080 --fps 30 --duration 30
Exit code 0 = passed, 1 = errors, 2 = could not run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import (UVSError, duration_of, ffprobe, load_json, parse_rate,  # noqa: E402
                        require_tools, shots_of, stream)


def analyze(video: Path, has_video: bool, has_audio: bool, black_min: float, black_pix_th: float, silence_min: float,
            freeze: bool) -> dict:
    # low pix_th = only (near) pure black counts, so dark brand backgrounds are not flagged
    vf = f"blackdetect=d={black_min}:pix_th={black_pix_th}"
    if freeze:
        vf += ",freezedetect=n=-60dB:d=3"
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video)]
    if has_video:
        cmd += ["-map", "0:v:0", "-vf", vf]
    if has_audio:
        cmd += ["-map", "0:a:0", "-af", f"silencedetect=n=-50dB:d={silence_min},ebur128=peak=true:framelog=verbose"]
    cmd += ["-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise UVSError("analysis failed (file may be corrupt):\n" + proc.stderr.strip()[-800:])
    log = proc.stderr
    res: dict = {"black": [], "silence": [], "frozen": []}
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", log):
        res["black"].append({"start": float(m[1]), "end": float(m[2]), "duration": float(m[3])})
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    ends = re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", log)
    for i, s in enumerate(starts):
        if i < len(ends):
            res["silence"].append({"start": max(0.0, s), "end": float(ends[i][0]), "duration": float(ends[i][1])})
        else:
            res["silence"].append({"start": max(0.0, s), "end": None, "duration": None})  # until end of file
    fstarts = re.findall(r"freeze_start: ([\d.]+)", log)
    fdurs = re.findall(r"freeze_duration: ([\d.]+)", log)
    for s, d in zip(fstarts, fdurs):
        res["frozen"].append({"start": float(s), "duration": float(d)})
    summary = log[log.rfind("Summary:"):] if "Summary:" in log else ""
    m_i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    m_p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    m_lra = re.search(r"LRA:\s+([\d.]+) LU", summary)

    def num(m):
        if not m:
            return None
        return float("-inf") if m[1] == "-inf" else float(m[1])
    res["integrated_lufs"] = num(m_i)
    res["true_peak_dbtp"] = num(m_p)
    res["lra_lu"] = num(m_lra)
    return res


def parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        tl = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if tl is None:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[tl].strip())
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        cues.append({"start": start, "end": end, "lines": lines[tl + 1:]})
    return cues


def check_captions(path: Path, duration: float, max_cps: float, max_line: int, errors: list, warns: list) -> dict:
    cues = parse_srt(path)
    if not cues:
        errors.append(f"captions: no cues parsed from {path}")
        return {"cues": 0}
    prev_end = 0.0
    for i, c in enumerate(cues, 1):
        d = c["end"] - c["start"]
        chars = len(re.sub(r"\s", "", "".join(c["lines"])))
        if d <= 0:
            errors.append(f"captions: cue {i} has non-positive duration")
            continue
        if c["end"] > duration + 0.1:
            errors.append(f"captions: cue {i} ends at {c['end']:.2f}s, after video end {duration:.2f}s")
        if c["start"] < prev_end - 0.01:
            warns.append(f"captions: cue {i} overlaps previous cue")
        if d < 0.7:
            warns.append(f"captions: cue {i} on screen only {d:.2f}s")
        if chars / d > max_cps:
            warns.append(f"captions: cue {i} reading speed {chars / d:.1f} chars/s > {max_cps}")
        if len(c["lines"]) > 2:
            warns.append(f"captions: cue {i} has {len(c['lines'])} lines (max 2)")
        for ln in c["lines"]:
            if len(ln) > max_line:
                warns.append(f"captions: cue {i} line has {len(ln)} chars > {max_line}")
        prev_end = c["end"]
    return {"cues": len(cues)}


def extract_frames(video: Path, out_dir: Path, duration: float, n: int, shots: list[dict] | None) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    points: list[tuple[str, float]] = []
    if shots:
        t = 0.0
        for s in shots:
            d = float(s["duration_s"])
            points.append((f"{s['id']}.jpg", min(t + d / 2, max(0.0, duration - 0.05))))
            t += d
    else:
        points = [(f"frame_{i:02d}.jpg", duration * (i + 0.5) / n) for i in range(n)]
    for name, t in points:
        dest = out_dir / name
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-q:v", "3", str(dest)], capture_output=True)
        if dest.is_file():
            written.append(str(dest))
    cols = 4
    rows = max(2, -(-max(len(points), n) // cols))
    tiles = cols * rows
    sheet = out_dir / "contact_sheet.jpg"
    with tempfile.TemporaryDirectory() as td:
        for i in range(tiles):  # seek per tile: exact timestamps, no fps-filter sampling artifacts
            t = duration * (i + 0.5) / tiles
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=480:-2", str(Path(td) / f"t{i:03d}.png")], capture_output=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(Path(td) / "t%03d.png"),
                        "-vf", f"tile={cols}x{rows}:padding=4:margin=4", "-frames:v", "1", "-q:v", "3", str(sheet)],
                       capture_output=True)
    if sheet.is_file():
        written.append(str(sheet))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--project")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--fps", type=float)
    ap.add_argument("--duration", type=float, help="expected seconds")
    ap.add_argument("--duration-tolerance", type=float, default=0.25)
    ap.add_argument("--min-duration", type=float, default=0.1)
    ap.add_argument("--allow-no-audio", action="store_true")
    ap.add_argument("--target-lufs", type=float, default=None, help="default: brief.delivery.loudness_lufs or -14")
    ap.add_argument("--lufs-tolerance", type=float, default=2.0)
    ap.add_argument("--max-peak", type=float, default=-1.0, help="max true peak dBTP")
    ap.add_argument("--black-min", type=float, default=0.5)
    ap.add_argument("--black-pix-th", type=float, default=0.02)
    ap.add_argument("--silence-min", type=float, default=2.0)
    ap.add_argument("--freeze", action="store_true", help="warn on frozen video >= 3s (noisy for title cards)")
    ap.add_argument("--captions", help="SRT to check (project mode: captions/captions.srt if present)")
    ap.add_argument("--max-cps", type=float, default=None, help="caption chars/s (default 12 ko, 17 other)")
    ap.add_argument("--max-line", type=int, default=None, help="caption chars/line (default 20 ko, 42 other)")
    ap.add_argument("--frames-dir")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--report", help="write JSON report here")
    a = ap.parse_args()
    try:
        require_tools("ffmpeg", "ffprobe")
        brief, shots, project = {}, None, None
        if a.project:
            project = Path(a.project).resolve()
            brief = load_json(project / "brief.json")
            if (project / "storyboard.json").is_file():
                shots = shots_of(load_json(project / "storyboard.json"))
        video = Path(a.video) if a.video else (project / "renders" / "final.mp4" if project else None)
        if video is None:
            ap.error("give a video path or --project")
        if not video.is_file():
            raise UVSError(f"video not found: {video}")
        exp_w = a.width or brief.get("width")
        exp_h = a.height or brief.get("height")
        exp_fps = a.fps or brief.get("fps")
        exp_dur = a.duration or (sum(float(s["duration_s"]) for s in shots) if shots else None)
        lang = brief.get("language", "ko")
        cjk = lang in ("ko", "ja", "zh")
        target = a.target_lufs if a.target_lufs is not None else (brief.get("delivery", {}) or {}).get("loudness_lufs", -14)

        info = ffprobe(video)
        v, au = stream(info, "video"), stream(info, "audio")
        dur = duration_of(info)
        errors: list[str] = []
        warns: list[str] = []
        if v is None:
            errors.append("no video stream")
        if au is None and not a.allow_no_audio:
            errors.append("no audio stream (platforms and players expect one; use --allow-no-audio to waive)")
        if dur < a.min_duration:
            errors.append(f"duration {dur:.2f}s below minimum {a.min_duration}s")
        if exp_dur and abs(dur - exp_dur) > a.duration_tolerance:
            errors.append(f"duration {dur:.2f}s != expected {exp_dur:.2f}s (±{a.duration_tolerance})")
        fps = None
        if v:
            if exp_w and v.get("width") != exp_w:
                errors.append(f"width {v.get('width')} != {exp_w}")
            if exp_h and v.get("height") != exp_h:
                errors.append(f"height {v.get('height')} != {exp_h}")
            fps = parse_rate(v.get("avg_frame_rate")) or parse_rate(v.get("r_frame_rate"))
            if exp_fps and (fps is None or abs(fps - float(exp_fps)) > 0.01):
                errors.append(f"fps {fps} != {exp_fps}")
            if v.get("pix_fmt") != "yuv420p":
                errors.append(f"pix_fmt {v.get('pix_fmt')} (use yuv420p for player compatibility)")
            if v.get("codec_name") not in ("h264", "hevc", "av1", "vp9"):
                warns.append(f"video codec {v.get('codec_name')} may not be accepted by all platforms")
        if au and int(au.get("sample_rate", 0) or 0) not in (44100, 48000):
            warns.append(f"audio sample rate {au.get('sample_rate')}")
        fmt = info["format"].get("format_name", "")
        if "mp4" in fmt or "mov" in fmt:
            with video.open("rb") as fh:
                head = fh.read(1 << 16)
            if b"moov" not in head:
                warns.append("moov atom not at file start (add -movflags +faststart for web streaming)")

        an = analyze(video, v is not None, au is not None, a.black_min, a.black_pix_th, a.silence_min, a.freeze) if (v or au) else {}
        for b in an.get("black", []):
            warns.append(f"black frames {b['start']:.2f}-{b['end']:.2f}s ({b['duration']:.2f}s)")
        for f in an.get("frozen", []):
            warns.append(f"frozen video from {f['start']:.2f}s for {f['duration']:.2f}s")
        lufs, peak = an.get("integrated_lufs"), an.get("true_peak_dbtp")
        silences = an.get("silence", [])
        whole_silent = au is not None and (lufs is None or lufs == float("-inf") or lufs < -60)
        if whole_silent:
            warns.append("audio track is silent (no voiceover/music mixed?)")
        else:
            for s in silences:
                end = f"{s['end']:.2f}s" if s["end"] is not None else "end"
                warns.append(f"silence {s['start']:.2f}s-{end}")
            if lufs is not None and abs(lufs - target) > a.lufs_tolerance:
                warns.append(f"integrated loudness {lufs:.1f} LUFS vs target {target} (assemble.py --loudnorm {target})")
            if peak is not None and peak > a.max_peak:
                errors.append(f"true peak {peak:.1f} dBTP > {a.max_peak} (clipping risk; use --loudnorm)")

        cap_path = Path(a.captions) if a.captions else (
            project / "captions" / "captions.srt" if project and (project / "captions" / "captions.srt").is_file() else None)
        cap = None
        if cap_path:
            cap = check_captions(cap_path, dur, a.max_cps or (12 if cjk else 17), a.max_line or (20 if cjk else 42),
                                 errors, warns)

        frames_dir = Path(a.frames_dir) if a.frames_dir else (project / "qa" / "frames" if project else None)
        frames = extract_frames(video, frames_dir, dur, a.frames, shots) if (frames_dir and v and dur > 0) else []

        report = {
            "passed": not errors,
            "video": str(video.resolve()),
            "errors": errors,
            "warnings": warns,
            "measured": {
                "duration": round(dur, 3), "width": v.get("width") if v else None, "height": v.get("height") if v else None,
                "fps": fps, "pix_fmt": v.get("pix_fmt") if v else None, "video_codec": v.get("codec_name") if v else None,
                "audio_codec": au.get("codec_name") if au else None,
                "integrated_lufs": lufs if lufs != float("-inf") else None,
                "true_peak_dbtp": peak if peak != float("-inf") else None, "lra_lu": an.get("lra_lu"),
                "black_segments": an.get("black", []), "silence_segments": silences, "captions": cap,
            },
            "expected": {"width": exp_w, "height": exp_h, "fps": exp_fps, "duration": exp_dur, "target_lufs": target},
            "frames_for_review": frames,
            "manual_checks": [
                "Look at every frame in frames_for_review: text typos, Hangul rendering, logo/brand colors",
                "Captions and key text inside the safe area (~5% margin each side; avoid bottom 10-15% on Shorts/Reels UI)",
                "Listen once end-to-end: voice intelligibility, music not masking speech, no clicks at cuts",
                "Rights: every asset/music/font/model listed in provenance.json with a license",
            ],
        }
        report_path = Path(a.report) if a.report else (project / "qa" / "qa_report.json" if project else None)
        text = json.dumps(report, indent=2, ensure_ascii=False)
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0 if not errors else 1
    except UVSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
