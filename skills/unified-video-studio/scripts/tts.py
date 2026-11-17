#!/usr/bin/env python3
"""Synthesize per-shot voiceover into project/assets/voice/<shot-id>.<ext>.

assemble.py automatically mixes assets/voice/<shot-id>.(wav|mp3|m4a) into that shot.

Providers:
  --provider edge   : edge-tts (pip install edge-tts). NOTE: sends the text to
                      Microsoft's online TTS service; get user consent first.
  --provider cmd    : any local/offline TTS via a command template with
                      {text_file} and {out} placeholders, e.g.
                      --cmd "piper -m ko.onnx -f {out} < {text_file}"   (shell)

Usage: tts.py --project project/ [--provider edge] [--voice ko-KR-SunHiNeural]
              [--rate +0%] [--only shot-001] [--force]
Warns when the generated audio is longer than its shot.
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import (UVSError, duration_of, ffprobe, load_json, require_tools, shots_of,  # noqa: E402
                        voice_offset_of, warn)

DEFAULT_VOICES = {"ko": "ko-KR-SunHiNeural", "en": "en-US-AriaNeural", "ja": "ja-JP-NanamiNeural"}


def edge_cmd() -> list[str]:
    if shutil.which("edge-tts"):
        return ["edge-tts"]
    try:
        import importlib.util
        if importlib.util.find_spec("edge_tts"):
            return [sys.executable, "-m", "edge_tts"]
    except (ImportError, ValueError):
        pass
    if shutil.which("uvx"):
        return ["uvx", "--from", "edge-tts", "edge-tts"]
    raise UVSError("edge-tts not installed (pip install edge-tts / uv tool install edge-tts), or use --provider cmd")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--provider", choices=["edge", "cmd"], default="edge")
    ap.add_argument("--voice")
    ap.add_argument("--rate", default="+0%", help="edge-tts speaking rate, e.g. +10%%")
    ap.add_argument("--cmd", help="command template for --provider cmd ({text_file}, {out})")
    ap.add_argument("--ext", default=None, help="output extension (default mp3 for edge, wav for cmd)")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    try:
        require_tools("ffprobe")
        project = Path(a.project).resolve()
        brief = load_json(project / "brief.json")
        shots = shots_of(load_json(project / "storyboard.json"))
        lang = brief.get("language", "ko")
        ext = a.ext or ("mp3" if a.provider == "edge" else "wav")
        if a.provider == "cmd" and not a.cmd:
            raise UVSError("--provider cmd needs --cmd")
        base = edge_cmd() if a.provider == "edge" else None
        voice = a.voice or DEFAULT_VOICES.get(lang, DEFAULT_VOICES["en"])
        only = set(a.only.split(",")) if a.only else None
        vdir = project / "assets" / "voice"
        vdir.mkdir(parents=True, exist_ok=True)
        made = 0
        for shot in shots:
            text = (shot.get("voiceover") or "").strip()
            if not text or (only and shot["id"] not in only):
                continue
            out = vdir / f"{shot['id']}.{ext}"
            if out.exists() and not a.force:
                print(f"skip  {shot['id']} (exists)")
                continue
            with tempfile.TemporaryDirectory() as td:
                tf = Path(td) / "text.txt"
                tf.write_text(text, encoding="utf-8")
                if a.provider == "edge":
                    cmd = [*base, "--voice", voice, f"--rate={a.rate}", "--file", str(tf), "--write-media", str(out)]
                    proc = subprocess.run(cmd, capture_output=True, text=True)
                else:
                    line = a.cmd.format(text_file=shlex.quote(str(tf)), out=shlex.quote(str(out)))
                    proc = subprocess.run(line, shell=True, capture_output=True, text=True)
            if proc.returncode != 0 or not out.is_file():
                raise UVSError(f"TTS failed for {shot['id']}: {(proc.stderr or proc.stdout).strip()[-800:]}")
            vd = duration_of(ffprobe(out))
            made += 1
            print(f"voice {shot['id']}: {vd:.2f}s / shot {shot['duration_s']}s -> {out}")
            off = voice_offset_of(shot)
            if off + vd > float(shot["duration_s"]) - 0.1:
                warn(f"{shot['id']}: voice ({vd:.2f}s, starting at {off:.2f}s) does not fit shot ({shot['duration_s']}s); "
                     "shorten text, raise --rate, or lengthen the shot")
        print(f"generated {made} voice file(s); record provider/voice in provenance.json")
    except UVSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
