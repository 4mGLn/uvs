#!/usr/bin/env python3
"""Report which video engines and prerequisites are actually available.

Exit code: 0 if all *required* items pass, 1 otherwise.
Usage: doctor.py [--json] [--save project/qa/environment.json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import find_korean_font  # noqa: E402


def version_of(cmd: list[str], pattern: str = r"(\d+(?:\.\d+)+)") -> str | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(pattern, (proc.stdout or "") + (proc.stderr or ""))
    return m.group(1) if m else ("unknown" if proc.returncode == 0 else None)


def ffmpeg_features() -> dict:
    feats = {}
    try:
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        fil = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    except OSError:
        return feats
    feats["libx264"] = " libx264 " in enc
    feats["aac"] = " aac " in enc
    for f in ("drawtext", "subtitles", "loudnorm", "blackdetect", "silencedetect", "freezedetect", "ebur128"):
        feats[f] = re.search(rf"\s{f}\s", fil) is not None
    return feats


def gpu_info() -> dict:
    if shutil.which("nvidia-smi"):
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            gpus = []
            for line in proc.stdout.strip().splitlines():
                name, mem = [x.strip() for x in line.rsplit(",", 1)]
                gpus.append({"name": name, "vram_mb": int(float(mem))})
            return {"vendor": "nvidia", "gpus": gpus}
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return {"vendor": "apple", "gpus": [{"name": "Apple Silicon (unified memory)", "vram_mb": None}]}
    return {"vendor": None, "gpus": []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--save", help="also write the JSON report to this path")
    a = ap.parse_args()

    report: dict = {"platform": f"{platform.system()} {platform.release()} {platform.machine()}",
                    "python": platform.python_version(), "required": {}, "optional": {}}

    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    report["required"]["ffmpeg"] = {"path": ff, "version": version_of(["ffmpeg", "-version"], r"ffmpeg version (\S+)") if ff else None}
    report["required"]["ffprobe"] = {"path": fp}
    feats = ffmpeg_features() if ff else {}
    report["ffmpeg_features"] = feats
    for must in ("libx264", "aac", "drawtext"):
        report["required"][f"ffmpeg:{must}"] = {"ok": bool(feats.get(must))}

    font = find_korean_font()
    report["required"]["korean_font"] = {"path": font[0] if font else None, "family": font[1] if font else None}

    opt = report["optional"]
    for name, cmd in {
        "node": ["node", "--version"],
        "npx": ["npx", "--version"],
        "blender": ["blender", "--version"],
        "manim": ["manim", "--version"],
        "auto-editor": ["auto-editor", "--version"],
        "whisperx": ["whisperx", "--help"],
        "edge-tts": ["edge-tts", "--version"],
        "uvx": ["uvx", "--version"],
        "fc-match": None,
    }.items():
        path = shutil.which(name)
        opt[name] = {"path": path, "version": version_of(cmd) if (path and cmd) else None}
    for mod in ("whisperx", "torch", "edge_tts"):
        try:
            found = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            found = False
        opt[f"python:{mod}"] = {"ok": found}
    report["gpu"] = gpu_info()

    def ok(v: dict) -> bool:
        return bool(v.get("ok", v.get("path")))

    req_ok = all(ok(v) for v in report["required"].values())
    report["required_ok"] = req_ok
    nodever = opt["node"]["version"] or ""
    report["engines_ready"] = {
        "ffmpeg-title/image (built-in)": req_ok,
        "remotion/hyperframes (needs node>=18 + npx)": bool(opt["npx"]["path"]) and nodever.split(".")[0].isdigit() and int(nodever.split(".")[0]) >= 18,
        "blender": bool(opt["blender"]["path"]),
        "manim": bool(opt["manim"]["path"]),
        "auto-editor": bool(opt["auto-editor"]["path"]),
        "whisperx": bool(opt["whisperx"]["path"] or opt["python:whisperx"]["ok"]),
        # hardware check only: whether ComfyUI itself is installed/running is not probed
        "comfyui (GPU with >=8GB VRAM; ComfyUI install not checked)": any((g.get("vram_mb") or 0) >= 8000 for g in report["gpu"]["gpus"]),
        # tts.py falls back to `uvx --from edge-tts edge-tts`, so uvx alone is enough
        "tts (edge-tts, or via uvx)": bool(opt["edge-tts"]["path"] or opt["python:edge_tts"]["ok"] or opt["uvx"]["path"]),
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if a.save:
        Path(a.save).parent.mkdir(parents=True, exist_ok=True)
        Path(a.save).write_text(text + "\n", encoding="utf-8")
    if a.json:
        print(text)
    else:
        print("== required ==")
        for k, v in report["required"].items():
            print(f"  [{'OK' if ok(v) else 'MISSING'}] {k} {v.get('version') or v.get('family') or v.get('path') or ''}".rstrip())
        print("== engines ==")
        for k, v in report["engines_ready"].items():
            print(f"  [{'ready' if v else ' -- '}] {k}")
        g = report["gpu"]["gpus"]
        print("== gpu ==\n  " + (", ".join(f"{x['name']} ({x['vram_mb']} MB)" for x in g) if g else "none detected"))
        missing = [k for k, v in report["engines_ready"].items() if not v]
        if missing:
            print("hint: '--' means not installed (or, for comfyui, not enough VRAM); install steps are in\n"
                  "      references/engines/<engine>.md. Built-in shots work without any of them.")
        if not report["required"]["korean_font"]["path"]:
            print("hint: install a Hangul font, e.g. `sudo apt install fonts-noto-cjk` or fonts-nanum")
        print(f"\nrequired_ok={req_ok}  (full report: --json)")
    return 0 if req_ok else 1


if __name__ == "__main__":
    sys.exit(main())
