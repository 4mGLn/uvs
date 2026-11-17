#!/usr/bin/env python3
"""One-command pipeline: validate -> render built-ins -> captions -> assemble -> QA.

Usage:
  build.py --project project/ [--placeholders] [--burn-subs] [--music assets/music.mp3 --duck]
           [--no-loudnorm] [--fit contain|cover] [--strict]
--placeholders renders labeled cards for shots whose engine clip is not ready yet
(animatic). Without it, every non-built-in shot must already have its clip.
Loudness normalization runs automatically when voice files or music exist.
Exit code: 0 = QA passed, 1 = validation/QA errors, 2 = a step could not run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from uvs_common import load_json, shots_of  # noqa: E402


def step(name: str, args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    print(f"\n== {name} ==", flush=True)
    proc = subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], text=True,
                          capture_output=capture)
    return proc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--placeholders", action="store_true")
    ap.add_argument("--burn-subs", action="store_true", help="burn captions/captions.srt into the video")
    ap.add_argument("--music")
    ap.add_argument("--music-db", type=float, default=-20.0)
    ap.add_argument("--duck", action="store_true")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--fit", choices=["contain", "cover"], default="contain")
    ap.add_argument("--strict", action="store_true", help="validation warnings fail the build")
    ap.add_argument("--force", action="store_true", help="re-render built-in clips")
    a = ap.parse_args()
    proj = str(Path(a.project).resolve())

    v = step("validate", ["validate.py", "--project", proj] + (["--strict"] if a.strict else []))
    if v.returncode != 0:
        print("\nbuild stopped: fix storyboard/brief errors above")
        return 1 if v.returncode == 1 else 2

    r = step("render built-in shots", ["render_builtin.py", "--project", proj]
             + (["--placeholders"] if a.placeholders else []) + (["--force"] if a.force else []))
    if r.returncode != 0:
        return 2

    shots = shots_of(load_json(Path(proj) / "storyboard.json"))
    srt = Path(proj) / "captions" / "captions.srt"
    has_vo_text = any((s.get("voiceover") or "").strip() for s in shots)
    if has_vo_text or srt.is_file():  # also clears a stale SRT when voiceover was removed
        c = step("captions (script-timed)", ["make_captions.py", "--project", proj])
        if c.returncode != 0:
            return 2
    has_voice = any((Path(proj) / "assets" / "voice").glob("*.*")) or any(s.get("voiceover_audio") for s in shots)
    asm = ["assemble.py", "--project", proj, "--fit", a.fit]
    if a.placeholders:
        asm.append("--allow-placeholders")
    if a.burn_subs:
        if not srt.is_file():
            print(f"--burn-subs given but {srt} does not exist (no voiceover text?)")
            return 1
        asm += ["--subtitles", str(srt)]
    if a.music:
        asm += ["--music", str(Path(a.music).resolve()), "--music-db", str(a.music_db)] + (["--duck"] if a.duck else [])
    if (has_voice or a.music) and not a.no_loudnorm:
        brief = load_json(Path(proj) / "brief.json")
        target = (brief.get("delivery", {}) or {}).get("loudness_lufs", -14)
        asm += ["--loudnorm", str(target)]
    s = step("assemble", asm)
    if s.returncode != 0:
        return 2

    q = step("quality gate", ["quality_gate.py", "--project", proj], capture=True)
    try:
        rep = json.loads(q.stdout)
    except json.JSONDecodeError:
        print(q.stderr or q.stdout)
        return 2
    print(f"passed: {rep['passed']}")
    for e in rep["errors"]:
        print(f"  ERROR   {e}")
    for w in rep["warnings"]:
        print(f"  warning {w}")
    print(f"report: {proj}/qa/qa_report.json\nframes: {proj}/qa/frames/ (review them)\nvideo:  {rep['video']}")
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
