# Manim Community (`engine: manim`)

Best for: math, algorithms, diagrams that transform step by step.
Needs: `manim` (Manim CE, `pip install manim` / `uv tool install manim`) and, for
`MathTex`/`Tex`, a LaTeX distribution.

## Per shot
`scenes/shot-004/scene.py`:
```python
from manim import *

class Shot004(Scene):
    def construct(self):
        title = Text("이진 탐색", font="Noto Sans CJK KR").scale(0.9)
        self.play(Write(title), run_time=1.5)
        self.play(title.animate.to_edge(UP))
        eq = MathTex(r"O(\log n)")
        self.play(FadeIn(eq))
        self.wait(6 - 1.5 - 1 - 1)   # pad so the scene equals duration_s
```
Render at the brief's size/fps and copy into the clip slot:
```bash
manim render -qh -r 1920,1080 --fps 30 --media_dir scenes/shot-004/media \
  scenes/shot-004/scene.py Shot004
cp scenes/shot-004/media/videos/scene/*/Shot004.mp4 renders/clips/shot-004.mp4
```
- Korean must use `Text(..., font=...)` with an installed Hangul font; Korean inside
  `Tex` needs the `kotex` package — prefer `Text` for Korean, `MathTex` for formulas.
- Sum of `run_time` + `wait` must equal `duration_s` (assemble trims/holds otherwise).
- Output path pattern varies with quality flags; check the printed "File ready at" line.
