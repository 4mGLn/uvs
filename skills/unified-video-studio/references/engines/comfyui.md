# ComfyUI generative video (`engine: comfyui`)

Best for: short generative B-roll that cannot be shot or built.
Needs: a running ComfyUI (default `http://127.0.0.1:8188`), a video model (e.g. Wan 2.x)
and enough GPU memory. Check `doctor.py` `gpu`: below ~8 GB VRAM, local video
generation is generally impractical — propose a cloud GPU or a still `image` shot.
Exact VRAM needs depend on model size, resolution and offloading; check the model card.

## Rules
- Get the user's OK on model choice and its license (commercial use terms vary).
- Generate at the model's native resolution/fps, then let `assemble.py` scale
  (`--fit cover`) and conform fps — or upscale/interpolate in the workflow.
- Save the workflow in API format to `scenes/<shot-id>/workflow.json`; record model,
  seed, prompt, negative prompt in `provenance.json` (`generations`).
- Queue via the HTTP API (`POST /prompt` with `{"prompt": <api-workflow>}`), poll
  `/history/<prompt_id>`, then copy the output from ComfyUI's `output/` folder to
  `renders/clips/<shot-id>.mp4` (re-encode to H.264 yuv420p if needed).
- Generated clips are usually 2-5 s; plan shots accordingly or loop/hold carefully.
- Review every generated clip for artifacts, text gibberish, faces/logos you have no
  rights to — reject rather than ship.
