#!/usr/bin/env python3
"""End-to-end smoke test using only FFmpeg (no network, no external engines).

Builds a 12s Korean project with: title card, image shot (zoom + lower third),
footage shot (wrong size/fps, no audio), a placeholder shot, per-shot voice files
(a sine tone stands in for TTS via tts.py --provider cmd), music with ducking,
burned-in captions, fades and loudness normalization. Then checks the QA report
and a few failure paths.

Usage: python3 tests/smoke_test.py [--keep DIR]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FAILS: list[str] = []


def sh(args: list[str], expect: int = 0, **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, **kw)
    if proc.returncode != expect:
        FAILS.append(f"{' '.join(map(str, args[:3]))}: rc={proc.returncode} (expected {expect})\n"
                     f"{proc.stdout[-800:]}\n{proc.stderr[-1500:]}")
    return proc


def py(script: str, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
    return sh([sys.executable, "-I", str(SCRIPTS / script), *args], expect=expect)


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def new_project(base: Path, name: str, shots: list[dict], **brief_kw) -> Path:
    proj = base / name
    py("init_project.py", str(proj), "--title", name)
    brief = json.loads((proj / "brief.json").read_text(encoding="utf-8"))
    brief.update({"width": 640, "height": 360, **brief_kw})
    brief["duration_s"] = sum(s["duration_s"] for s in shots)
    (proj / "brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    (proj / "storyboard.json").write_text(json.dumps({"shots": shots}, ensure_ascii=False), encoding="utf-8")
    return proj


def probe(path: Path) -> dict:
    out = sh(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout
    return json.loads(out or "{}")


def validate_errors(base: Path, name: str, shots: list[dict]) -> str:
    proj = new_project(base, name, shots)
    r = py("validate.py", "--project", str(proj), expect=1)
    return " ".join(json.loads(r.stdout or "{}").get("errors", []))


def regressions(base: Path) -> None:
    print("regressions")
    # literal %, braces and backslashes must render (drawtext expansion=none)
    proj = new_project(base, "pct", [{"id": "a", "duration_s": 1, "engine": "ffmpeg-title",
                                      "on_screen_text": "최대 50% 할인 %{x} C:\\a", "style": {"bg": "#000000"}}])
    py("render_builtin.py", "--project", str(proj))
    r = sh(["ffmpeg", "-v", "error", "-ss", "0.9", "-i", str(proj / "renders/clips/a.mp4"), "-frames:v", "1",
            "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-"])
    ymax = [float(x.split("=")[1]) for x in r.stdout.splitlines() if "YMAX=" in x]
    check(bool(ymax) and ymax[0] > 100, "text containing % is drawn")

    # frame-exact timeline: 20 x 1.35s @30 and 10 x 2.5s @29.97 must not drift
    for name, fps, n, d in (("f30", 30, 20, 1.35), ("ntsc", 29.97, 10, 2.5)):
        shots = [{"id": f"s{i}", "duration_s": d, "engine": "ffmpeg-title", "on_screen_text": str(i)} for i in range(n)]
        proj = new_project(base, name, shots, fps=fps)
        sh([sys.executable, "-I", str(SCRIPTS / "build.py"), "--project", str(proj)])
        rep = json.loads((proj / "qa/qa_report.json").read_text(encoding="utf-8"))
        check(rep["passed"] and abs(rep["measured"]["duration"] - n * d) < 0.05,
              f"{name}: no drift ({rep['measured']['duration']} vs {n * d}, errors={rep['errors']})")

    # clip whose audio outlasts its video: no frame gap
    proj = new_project(base, "longaud", [{"id": "a", "duration_s": 4, "engine": "footage", "clip": "assets/c.mp4"}])
    sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=2", "-f", "lavfi",
        "-i", "sine=d=5", "-pix_fmt", "yuv420p", str(proj / "assets/c.mp4")])
    py("assemble.py", "--project", str(proj))
    vs = next(s for s in probe(proj / "renders/final.mp4")["streams"] if s["codec_type"] == "video")
    check(int(vs.get("nb_read_frames", 0)) == 120, f"long-audio clip -> 120 frames (got {vs.get('nb_read_frames')})")

    # validator edge cases
    ok_proj = new_project(base, "shortcut", [{"id": "a", "duration_s": 0.5, "engine": "ffmpeg-title", "on_screen_text": "x"}])
    check(py("validate.py", "--project", str(ok_proj)).returncode == 0, "0.5s cut shot is valid")
    errs = validate_errors(base, "fadeover", [
        {"id": "a", "duration_s": 8, "engine": "ffmpeg-title", "transition": "fade", "transition_s": 6},
        {"id": "b", "duration_s": 2, "engine": "ffmpeg-title"}])
    check("fades need" in errs, "fade longer than next shot is rejected")
    errs = validate_errors(base, "types", [
        {"id": "a", "duration_s": 2, "engine": "ffmpeg-title", "on_screen_text": 123},
        {"id": "b", "duration_s": 2, "engine": "ffmpeg-title", "style": {"font_size": "96"}},
        {"id": "c", "duration_s": 2, "engine": "ffmpeg-title", "voiceover_offset_s": -0.5},
        {"id": "d", "duration_s": 2, "engine": "image", "assets": None}])
    check(all(k in errs for k in ("on_screen_text", "font_size", "voiceover_offset_s", "'assets' must be a list")),
          "validator rejects wrong field types")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="build the project in this directory and keep it")
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found; cannot run smoke test")
        return 2
    base = Path(a.keep).resolve() if a.keep else Path(tempfile.mkdtemp(prefix="uvs-smoke-"))
    if a.keep and base.exists():
        shutil.rmtree(base)
    proj = base / "proj"
    try:
        print("init")
        py("init_project.py", str(proj), "--title", "스모크 테스트", "--duration", "12", "--height", "720")
        brief = json.loads((proj / "brief.json").read_text(encoding="utf-8"))
        check(brief["width"] == 1280 and brief["height"] == 720, "init sets 1280x720")

        # inputs
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=800x800:d=1", "-frames:v", "1",
            str(proj / "assets" / "photo.png")])
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=640x480:r=24:d=4",
            "-pix_fmt", "yuv420p", str(proj / "assets" / "footage clip's.mp4")])
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=20", "-af", "volume=-6dB",
            str(proj / "assets" / "music.wav")])

        sb = {"shots": [
            {"id": "s1", "duration_s": 3, "engine": "ffmpeg-title", "on_screen_text": "한글 타이틀 테스트",
             "voiceover": "안녕하세요. 스모크 테스트입니다.", "style": {"accent": "#F2AA4C", "subtitle": "부제목"},
             "transition": "fade", "transition_s": 0.6, "assets": []},
            {"id": "s2", "duration_s": 3, "engine": "image", "on_screen_text": "이미지 위 하단 자막",
             "voiceover": "이미지 장면입니다.", "transition": "cut",
             "assets": [{"path": "assets/photo.png", "type": "image", "source": "generated testsrc2", "license": "owned"}]},
            {"id": "s3", "duration_s": 3, "engine": "footage", "clip": "assets/footage clip's.mp4",
             "voiceover": "", "transition": "fade", "transition_s": 0.4, "assets": []},
            {"id": "s4", "duration_s": 3, "engine": "remotion", "on_screen_text": "대시보드 자리",
             "visual_direction": "chart", "voiceover": "마지막 장면입니다.", "transition": "fade", "assets": []},
        ]}
        (proj / "storyboard.json").write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")

        print("validate")
        r = py("validate.py", "--project", str(proj))
        check(r.returncode == 0, "valid storyboard passes")

        print("tts (fake provider)")
        fake = ("ffmpeg -v error -y -f lavfi -i sine=f=660:d=1.5 -af volume=-3dB {out}")
        py("tts.py", "--project", str(proj), "--provider", "cmd", "--cmd", fake)
        check(len(list((proj / "assets" / "voice").glob("*.wav"))) == 3, "3 voice files (shots with voiceover)")

        print("build")
        r = sh([sys.executable, "-I", str(SCRIPTS / "build.py"), "--project", str(proj), "--placeholders",
                "--burn-subs", "--music", str(proj / "assets" / "music.wav"), "--duck"])
        print(r.stdout[-1200:])
        rep = json.loads((proj / "qa" / "qa_report.json").read_text(encoding="utf-8"))
        m = rep["measured"]
        check(rep["passed"], f"QA passed (errors={rep['errors']})")
        check(abs(m["duration"] - 12) < 0.05, f"duration 12s (got {m['duration']})")
        check((m["width"], m["height"], m["fps"]) == (1280, 720, 30), "1280x720@30")
        check(m["integrated_lufs"] is not None and abs(m["integrated_lufs"] + 14) < 2.5,
              f"loudness near -14 LUFS (got {m['integrated_lufs']})")
        check(m["true_peak_dbtp"] is not None and m["true_peak_dbtp"] <= -1.0, f"true peak <= -1 (got {m['true_peak_dbtp']})")
        check(m["captions"] and m["captions"]["cues"] >= 3, "captions generated and checked")
        frames = [Path(f).name for f in rep["frames_for_review"]]
        check({"s1.jpg", "s2.jpg", "s3.jpg", "s4.jpg", "contact_sheet.jpg"} <= set(frames), "review frames per shot")

        print("failure paths")
        bad = json.loads(json.dumps(sb))
        bad["shots"][1]["id"] = "s1"
        bad["shots"][2]["engine"] = "premiere"
        bad["shots"][0]["start_s"] = 1
        (base / "bad").mkdir(exist_ok=True)
        (base / "bad" / "storyboard.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        shutil.copyfile(proj / "brief.json", base / "bad" / "brief.json")
        r = py("validate.py", "--project", str(base / "bad"), expect=1)
        out = json.loads(r.stdout or "{}")
        errs = " ".join(out.get("errors", []))
        check("duplicate id" in errs and "unknown engine" in errs and "start_s" in errs, "validator catches bad storyboard")
        (proj / "renders" / "placeholders" / "s4.mp4").unlink()
        r = py("assemble.py", "--project", str(proj), "-o", str(base / "y.mp4"), expect=2)
        check("missing clips" in r.stderr, "assemble refuses missing clips")
        r = py("assemble.py", str(proj / "renders" / "final.mp4"), "-o", str(proj / "renders" / "final.mp4"), expect=2)
        check("one of the inputs" in r.stderr, "assemble refuses to overwrite an input")
        r = py("quality_gate.py", str(proj / "renders" / "final.mp4"), "--width", "1920", expect=1)
        check("width" in r.stdout, "QA flags resolution mismatch")
        (base / "corrupt.mp4").write_bytes(b"not a video")
        r = py("quality_gate.py", str(base / "corrupt.mp4"), expect=2)
        check("error:" in r.stderr and "Traceback" not in r.stderr, "QA reports corrupt file without traceback")

        regressions(base)
    finally:
        if not a.keep:
            shutil.rmtree(base, ignore_errors=True)
        else:
            print(f"kept: {base}")
    print("\nRESULT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
    for f in FAILS:
        print("-", f)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
