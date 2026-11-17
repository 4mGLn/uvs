# Existing footage, cutting and transcription (`engine: footage`)

Use for interviews, talking heads, screen recordings, stock clips.

## Use a clip directly
Set `"engine": "footage", "clip": "assets/interview.mp4"` on the shot. For a sub-range,
cut it first (re-encode for frame accuracy):
```bash
ffmpeg -ss 00:01:05.0 -i assets/interview.mp4 -t 8 -c:v libx264 -crf 18 -pix_fmt yuv420p \
  -c:a aac renders/clips/shot-006.mp4
```
`assemble.py --fit cover` crops instead of letterboxing (e.g. 16:9 footage in 9:16).

## Remove silences (Auto-Editor)
```bash
auto-editor assets/raw.mp4 --margin 0.2s -o assets/raw_cut.mp4
```
Option names change between Auto-Editor versions — check `auto-editor --help`.
Review the result; aggressive thresholds clip word endings.

## Transcribe / real-timed captions (WhisperX)
```bash
ffmpeg -i renders/final.mp4 -vn -ac 1 -ar 16000 captions/final.wav
whisperx captions/final.wav --model large-v3 --language ko --output_format srt \
  --output_dir captions/ --compute_type int8    # int8 for CPU / small GPU
cp captions/final.srt captions/captions.srt     # then re-run build.py --burn-subs
```
- On < 6 GB VRAM use `--model medium` or CPU int8; large-v3 is slow but most accurate for Korean.
- Always proofread Korean transcripts (names, numbers, product terms) before burning in.
- `quality_gate.py` checks caption timing, reading speed and line length.
