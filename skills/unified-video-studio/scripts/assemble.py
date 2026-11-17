#!/usr/bin/env python3
"""Normalize clips to one format and join them into a delivery MP4.

Project mode (recommended) reads brief.json + storyboard.json:
  - clip per shot: shot "clip" or renders/clips/<id>.mp4 (renders/placeholders/<id>.mp4
    with --allow-placeholders)
  - each clip is conformed to the shot's duration_s (trim, or hold last frame)
  - transition "fade": fade to/from black over transition_s at the shot boundary
  - assets/voice/<id>.(wav|mp3|m4a) or shot "voiceover_audio" is mixed into that shot
  Default output: renders/final.mp4

Clip mode: assemble.py a.mp4 b.mp4 -o out.mp4 (straight concat, no conform)

Finishing options (both modes): --subtitles captions.srt (burn-in), --music bgm.mp3
[--music-db -20 --duck], --loudnorm [-14] (EBU R128 integrated target, LUFS).

Usage:
  assemble.py --project project/ [--allow-placeholders] [--subtitles project/captions/captions.srt]
              [--music project/assets/music.mp3 --duck] [--loudnorm]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import (UVSError, display_size, duration_of, ffprobe, find_korean_font,  # noqa: E402
                        fps_rate, fps_value, load_json, parse_rate, require_tools, resolve_clip,
                        shot_frame_bounds, shots_of, stream, video_duration, voice_offset_of, warn)

VOICE_EXTS = ("wav", "mp3", "m4a", "aac", "flac", "ogg")


def ffmpeg(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *cmd], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise UVSError("ffmpeg failed:\n" + proc.stderr.strip()[-2000:])


def normalize(src: Path, dest: Path, *, W: int, H: int, fps: float, fit: str, crf: int, preset: str,
              frames: int | None, samples: int | None, shot_duration: float | None, fade_in: float,
              fade_out: float, voice: Path | None, voice_offset: float, label: str) -> float:
    """Encode one segment with an exact frame count (and matching audio sample count)."""
    info = ffprobe(src)
    v = stream(info, "video")
    if v is None:
        raise UVSError(f"{label}: no video stream in {src}")
    has_audio = stream(info, "audio") is not None
    src_dur = video_duration(info)
    rate, fv = fps_rate(fps), fps_value(fps)
    vw, vh = display_size(v)
    if vw and vh and abs(vw / vh - W / H) > 0.01:
        how = "cropped to fill" if fit == "cover" else "letterboxed/pillarboxed"
        warn(f"{label}: aspect {vw}x{vh} differs from {W}x{H}; will be {how} (--fit)")
    src_fps = parse_rate(v.get("avg_frame_rate"))
    if src_fps and abs(src_fps - fv) > 0.01:
        warn(f"{label}: {src_fps:.3f}fps -> {fv:.3f}fps conversion (frames dropped/duplicated)")
    if frames is None:
        frames = max(1, round(src_dur * fv))
    out_dur = frames / fv
    if samples is None:
        samples = round(out_dur * 48000)
    if shot_duration and src_dur + 0.05 < shot_duration:
        warn(f"{label}: clip {src_dur:.2f}s < shot {shot_duration:.2f}s; holding last frame")
    elif shot_duration and src_dur > shot_duration + 0.5:
        warn(f"{label}: clip {src_dur:.2f}s > shot {shot_duration:.2f}s; trimming")

    if fit == "cover":
        geom = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    else:
        geom = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"
    # tpad always: guarantees enough frames even if the source video is short
    vf = [geom, "setsar=1", f"fps={rate}", "format=yuv420p",
          f"tpad=stop_mode=clone:stop_duration={max(0.0, out_dur - src_dur) + 1:.3f}"]
    if fade_in > 0:
        vf.append(f"fade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        vf.append(f"fade=t=out:st={max(0.0, out_dur - fade_out):.3f}:d={fade_out:.3f}")

    inputs = ["-i", str(src)]
    idx = 1
    if has_audio:
        a_src = "[0:a:0]"
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        a_src = f"[{idx}:a]"
        idx += 1
    af_chain = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    graph = [f"[0:v:0]{','.join(vf)}[v]", f"{a_src}{af_chain},apad[a0]"]
    a_last = "[a0]"
    if voice:
        inputs += ["-i", str(voice)]
        delay = int(round(max(0.0, voice_offset) * 1000))
        graph.append(f"[{idx}:a]{af_chain},adelay={delay}:all=1,apad[vo]")
        graph.append(f"{a_last}[vo]amix=inputs=2:duration=first:normalize=0[a1]")
        a_last = "[a1]"
        idx += 1
        vdur = duration_of(ffprobe(voice))
        if voice_offset + vdur > out_dur + 0.05:
            warn(f"{label}: voiceover ({vdur:.2f}s from {voice_offset:.2f}s) runs past shot end ({out_dur:.2f}s); it will be cut")
    achain = []
    if fade_in > 0:
        achain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        achain.append(f"afade=t=out:st={max(0.0, out_dur - fade_out):.3f}:d={fade_out:.3f}")
    achain.append(f"atrim=end_sample={samples}")
    graph.append(f"{a_last}{','.join(achain)}[a]")

    ffmpeg([*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
            "-frames:v", str(frames), "-r", rate,
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            # PCM in the intermediate avoids AAC priming gaps accumulating at every cut
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(dest)])
    return out_dur


def finish(joined: Path, out: Path, td: Path, *, vertical: bool, subtitles: Path | None, font_family: str | None,
           music: Path | None, music_db: float, duck: bool, loudnorm: float | None, crf: int, preset: str) -> None:
    total = duration_of(ffprobe(joined))
    inputs = ["-i", str(joined)]
    graph, vmap = [], "0:v"
    if subtitles:
        shutil.copyfile(subtitles, td / "subs.srt")  # relative name avoids filtergraph path escaping
        # libass scales SRT styles from a 288-px-high canvas: 20 -> ~7% of height (16:9);
        # vertical frames get a smaller font and a higher margin to clear Shorts/Reels UI (~bottom 20%)
        style = ("FontSize=10,Outline=1,Shadow=0,MarginV=62,BorderStyle=1" if vertical
                 else "FontSize=20,Outline=1.5,Shadow=0,MarginV=24,BorderStyle=1")
        if font_family:
            style = f"FontName={font_family}," + style
        graph.append(f"[0:v]subtitles=filename=subs.srt:charenc=UTF-8:force_style='{style}'[v]")
        vmap = "[v]"
    a_last = "[0:a]"
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        fade_st = max(0.0, total - 2.0)
        graph.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_db}dB,"
                     f"atrim=0:{total:.3f},afade=t=out:st={fade_st:.3f}:d=2[m]")
        if duck:
            graph.append("[0:a]asplit=2[prog][key]")
            graph.append("[m][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=500[md]")
            graph.append("[prog][md]amix=inputs=2:duration=first:normalize=0[mix]")
        else:
            graph.append("[0:a][m]amix=inputs=2:duration=first:normalize=0[mix]")
        a_last = "[mix]"
    if loudnorm is not None:
        graph.append(f"{a_last}loudnorm=I={loudnorm}:TP=-1.5:LRA=11,aresample=48000[aout]")
        a_last = "[aout]"
    amap = "0:a" if a_last == "[0:a]" else a_last
    cmd = [*inputs]
    if graph:
        cmd += ["-filter_complex", ";".join(graph)]
    cmd += ["-map", vmap, "-map", amap]
    cmd += (["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
            if subtitles else ["-c:v", "copy"])
    cmd += (["-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if amap != "0:a" else ["-c:a", "copy"])
    # loudnorm/amix can append a few audio frames; clamp to the video duration
    cmd += ["-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    ffmpeg(cmd, cwd=td)


def find_voice(shot: dict, project: Path) -> Path | None:
    if shot.get("voiceover_audio"):
        p = Path(shot["voiceover_audio"])
        p = p if p.is_absolute() else project / p
        if not p.is_file():
            raise UVSError(f"shot {shot['id']}: voiceover_audio not found: {p}")
        return p
    for ext in VOICE_EXTS:
        p = project / "assets" / "voice" / f"{shot['id']}.{ext}"
        if p.is_file():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="*", help="clip mode: input files in order")
    ap.add_argument("--project", help="project mode: directory with brief.json + storyboard.json")
    ap.add_argument("-o", "--output")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--fps", type=float)
    ap.add_argument("--fit", choices=["contain", "cover"], default="contain")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--allow-placeholders", action="store_true")
    ap.add_argument("--subtitles", help="SRT file to burn in")
    ap.add_argument("--font-family", help="subtitle font family (default: auto-detected Hangul font)")
    ap.add_argument("--music")
    ap.add_argument("--music-db", type=float, default=-20.0)
    ap.add_argument("--duck", action="store_true", help="lower music under program audio (sidechain)")
    ap.add_argument("--loudnorm", nargs="?", type=float, const=-14.0, default=None,
                    help="normalize to LUFS target (default -14 when flag given)")
    a = ap.parse_args()
    try:
        require_tools("ffmpeg", "ffprobe")
        if bool(a.project) == bool(a.clips):
            ap.error("use either --project or positional clips")
        jobs: list[dict] = []
        if a.project:
            project = Path(a.project).resolve()
            brief = load_json(project / "brief.json")
            shots = shots_of(load_json(project / "storyboard.json"))
            W = a.width or int(brief["width"])
            H = a.height or int(brief["height"])
            fps = a.fps or float(brief["fps"])
            out = Path(a.output).resolve() if a.output else project / "renders" / "final.mp4"
            missing, used_ph = [], []
            bounds = shot_frame_bounds(shots, fps)
            fv = fps_value(fps)
            for i, s in enumerate(shots):
                path, is_ph = resolve_clip(s, project, a.allow_placeholders)
                if path is None:
                    missing.append(s["id"])
                    continue
                if is_ph:
                    used_ph.append(s["id"])
                f0, f1 = bounds[i]
                prev_tr = shots[i - 1].get("transition", "cut") if i > 0 else "cut"
                prev_ts = float(shots[i - 1].get("transition_s", 0.6)) if i > 0 else 0
                tr, tsec = s.get("transition", "cut"), float(s.get("transition_s", 0.6))
                is_last = i == len(shots) - 1
                jobs.append(dict(src=path, label=s["id"], shot_duration=float(s["duration_s"]),
                                 frames=max(1, f1 - f0),
                                 samples=round(f1 / fv * 48000) - round(f0 / fv * 48000),
                                 fade_in=prev_ts / 2 if prev_tr == "fade" else 0.0,
                                 fade_out=(tsec if is_last else tsec / 2) if tr == "fade" else 0.0,
                                 voice=find_voice(s, project),
                                 voice_offset=voice_offset_of(s)))
            if missing:
                raise UVSError(f"missing clips for shots: {', '.join(missing)} "
                               "(render them, or run render_builtin.py --placeholders and pass --allow-placeholders)")
            if used_ph:
                warn(f"using PLACEHOLDER clips for: {', '.join(used_ph)} (animatic, not final)")
        else:
            W, H, fps = a.width or 1920, a.height or 1080, a.fps or 30
            if not a.output:
                ap.error("-o/--output is required in clip mode")
            out = Path(a.output).resolve()
            for c in a.clips:
                p = Path(c).resolve()
                if not p.is_file():
                    raise UVSError(f"missing input: {c}")
                jobs.append(dict(src=p, label=p.name, shot_duration=None, frames=None, samples=None,
                                 fade_in=0.0, fade_out=0.0, voice=None, voice_offset=0.0))
        if W % 2 or H % 2:
            raise UVSError("width and height must be even")
        if out in {j["src"].resolve() for j in jobs}:
            raise UVSError("output path is one of the inputs; choose another -o")
        subs = Path(a.subtitles).resolve() if a.subtitles else None
        if subs and not subs.is_file():
            raise UVSError(f"subtitles not found: {subs}")
        music = Path(a.music).resolve() if a.music else None
        if music and not music.is_file():
            raise UVSError(f"music not found: {music}")
        font_family = a.font_family
        if subs and not font_family:
            found = find_korean_font()
            font_family = found[1] if found else None
            if not found:
                warn("no Hangul font found; burned-in Korean subtitles may render as boxes")

        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tdir:
            td = Path(tdir)
            parts, total = [], 0.0
            for i, j in enumerate(jobs):
                dest = td / f"{i:04d}.mkv"
                total += normalize(j["src"], dest, W=W, H=H, fps=fps, fit=a.fit, crf=a.crf, preset=a.preset,
                                   frames=j["frames"], samples=j["samples"], shot_duration=j["shot_duration"],
                                   fade_in=j["fade_in"], fade_out=j["fade_out"],
                                   voice=j["voice"], voice_offset=j["voice_offset"], label=j["label"])
                parts.append(dest)
                print(f"normalized {j['label']}")
            (td / "concat.txt").write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
            joined = td / "joined.mp4"
            ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat.txt", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(joined)], cwd=td)
            if subs or music or a.loudnorm is not None:
                tmp_final = td / "final.mp4"
                finish(joined, tmp_final, td, vertical=H > W, subtitles=subs, font_family=font_family, music=music,
                       music_db=a.music_db, duck=a.duck, loudnorm=a.loudnorm, crf=a.crf, preset=a.preset)
                shutil.move(str(tmp_final), out)
            else:
                shutil.move(str(joined), out)
        print(f"wrote {out} ({total:.3f}s, {W}x{H}@{fps_rate(fps)})")
    except UVSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
