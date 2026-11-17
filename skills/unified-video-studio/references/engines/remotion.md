# Remotion (`engine: remotion`)

Best for: data visualization, dashboards, product promos, many shots in one React style.
Needs: Node ≥ 18 (`doctor.py`). License: free for individuals and small companies;
larger companies need a Remotion company license — check https://remotion.dev/license.

## One-time setup (per project)
```bash
cd <project>/scenes
npx create-video@latest remotion   # choose a blank/TypeScript template
cd remotion && npm install
```
Optional: the official agent skills (`remotion-dev/skills`) add Remotion best practices.

## Per shot
1. Register a composition whose size/fps/duration match the brief and shot:
   ```tsx
   <Composition id="shot-003" component={Shot003} width={1920} height={1080}
                fps={30} durationInFrames={Math.round(12 * 30)} />
   ```
2. Animate only from `useCurrentFrame()` / `interpolate()` / `spring()` — never
   `Date.now()`, CSS transitions or GSAP timelines driven by wall-clock time, or frames
   will differ between renders.
3. Fonts: load a Hangul font explicitly (e.g. `@remotion/google-fonts/NotoSansKR`) and
   wait for it (`delayRender`/`continueRender`) or Korean renders in a fallback font.
4. Render straight into the clip slot:
   ```bash
   npx remotion render src/index.ts shot-003 ../../renders/clips/shot-003.mp4 \
     --codec h264 --pixel-format yuv420p
   ```
   Pass data with `--props '{"title":"..."}'` or `--props props.json` for templated variants.
5. Preview interactively with `npx remotion studio` when iterating with the user.

Common failures: missing Chromium download behind proxies (set `--browser-executable`),
fonts not loaded before first frame, `durationInFrames` not matching the storyboard.
