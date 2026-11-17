#!/usr/bin/env python3
"""Generate an SRT caption file from storyboard voiceover text (script-timed captions).

Each shot's voiceover is split into readable cues (<= --max-chars per line, 2 lines)
and spread over the shot proportionally to text length. For captions timed to the
*actual* audio, transcribe the final mix with WhisperX instead (references/engines/footage.md).

Usage: make_captions.py --project project/ [--source voiceover|on_screen_text]
                        [--max-chars 18] [-o project/captions/captions.srt]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uvs_common import UVSError, load_json, shots_of, voice_offset_of  # noqa: E402

LEAD_IN = 0.15   # default lead-in when captioning on-screen text (voiceover uses voiceover_offset_s)
TAIL_GAP = 0.10  # breathing room at shot end


def ts(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。？！…])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def break_lines(sentence: str, max_chars: int) -> list[str]:
    """Greedy word wrap; words longer than max_chars are hard-split."""
    lines, cur = [], ""
    for word in sentence.split():
        while len(word) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= max_chars:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def cues_for(text: str, max_chars: int) -> list[str]:
    cues = []
    for sent in split_sentences(text):
        lines = break_lines(sent, max_chars)
        for i in range(0, len(lines), 2):
            cues.append("\n".join(lines[i:i + 2]))
    return cues


def build_srt(shots: list[dict], source: str, max_chars: int) -> tuple[str, int]:
    out, n, t0 = [], 0, 0.0
    for shot in shots:
        dur = float(shot["duration_s"])
        text = shot.get(source) or ""
        text = text.strip() if isinstance(text, str) else ""
        if text:
            cues = cues_for(text, max_chars)
            weights = [max(1, len(c.replace("\n", ""))) for c in cues]
            lead = min(voice_offset_of(shot) if source == "voiceover" else LEAD_IN, max(0.0, dur - 0.3))
            span = max(0.2, dur - lead - TAIL_GAP)
            cur = t0 + lead
            for cue, w in zip(cues, weights):
                d = span * w / sum(weights)
                n += 1
                out.append(f"{n}\n{ts(cur)} --> {ts(cur + d - 0.04)}\n{cue}\n")
                cur += d
        t0 += dur
    return "\n".join(out), n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--source", choices=["voiceover", "on_screen_text"], default="voiceover")
    ap.add_argument("--max-chars", type=int, default=None, help="per line (default 18 for ko/ja/zh, 42 otherwise)")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    try:
        project = Path(a.project).resolve()
        brief = load_json(project / "brief.json")
        shots = shots_of(load_json(project / "storyboard.json"))
        max_chars = a.max_chars or (18 if brief.get("language", "ko") in ("ko", "ja", "zh") else 42)
        srt, n = build_srt(shots, a.source, max_chars)
        out = Path(a.output) if a.output else project / "captions" / "captions.srt"
        if n == 0:
            if out.is_file():
                out.unlink()  # never leave stale captions to be burned in later
                print(f"no '{a.source}' text in storyboard; removed stale {out}")
            else:
                print(f"no '{a.source}' text in storyboard; nothing written")
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(srt, encoding="utf-8")
        print(f"wrote {n} cue(s) -> {out}")
    except UVSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
