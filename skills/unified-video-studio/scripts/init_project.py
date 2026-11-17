#!/usr/bin/env python3
"""Create a video project skeleton from the skill templates.

Usage: init_project.py project/ [--title T] [--duration 30] [--aspect 16:9|9:16|1:1|4:5]
                       [--height 1080] [--fps 30] [--lang ko] [--force]
Creates brief.json, storyboard.json, provenance.json and scenes/ assets/ renders/clips/
renders/placeholders/ captions/ qa/, then records the environment in qa/environment.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
DIRS = ["scenes", "assets", "assets/voice", "renders/clips", "renders/placeholders", "captions", "qa"]


def even(x: float) -> int:
    return int(round(x / 2) * 2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--title")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--aspect", choices=sorted(ASPECTS), default="16:9")
    ap.add_argument("--height", type=int, default=None, help="short side in px (default 1080)")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--lang")
    ap.add_argument("--force", action="store_true", help="overwrite existing brief/storyboard/provenance")
    a = ap.parse_args()

    proj = Path(a.project).resolve()
    for d in DIRS:
        (proj / d).mkdir(parents=True, exist_ok=True)

    for name in ("brief.json", "storyboard.json", "provenance.json"):
        dst = proj / name
        if dst.exists() and not a.force:
            print(f"keep  {dst} (exists; --force to overwrite)")
            continue
        shutil.copyfile(TEMPLATES / name, dst)
        print(f"write {dst}")

    brief_p = proj / "brief.json"
    brief = json.loads(brief_p.read_text(encoding="utf-8"))
    short = even(a.height or min(brief["width"], brief["height"]))
    aw, ah = ASPECTS[a.aspect]
    if aw >= ah:
        h = short
        w = even(short * aw / ah)
    else:
        w = short
        h = even(short * ah / aw)
    changed = {"width": w, "height": h} if (a.aspect != "16:9" or a.height) else {}
    if a.title:
        changed["title"] = a.title
    if a.duration:
        changed["duration_s"] = a.duration
    if a.fps:
        changed["fps"] = int(a.fps) if float(a.fps).is_integer() else a.fps
    if a.lang:
        changed["language"] = a.lang
    if a.aspect != "16:9":
        delivery = dict(brief.get("delivery") or {})
        delivery["platform"] = {"9:16": "shorts/reels", "1:1": "social-square", "4:5": "instagram-feed"}[a.aspect]
        changed["delivery"] = delivery
    if changed:
        brief.update(changed)
        brief_p.write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"brief: {changed}")
        if "duration_s" in changed:
            print("note: storyboard template is 30s; adjust shot durations to match duration_s")

    subprocess.run([sys.executable, str(HERE / "doctor.py"), "--save", str(proj / "qa" / "environment.json")])
    print(f"\nnext: edit {proj}/storyboard.json, then\n"
          f"  python3 {HERE}/build.py --project {proj} --placeholders   # animatic preview")
    return 0


if __name__ == "__main__":
    sys.exit(main())
