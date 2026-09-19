# Local AI Media Workflows

Shorts Studio can talk to a local ComfyUI instance at `http://127.0.0.1:8188`.

## AI images

No workflow file is required for standard checkpoint-based image generation.

Once ComfyUI is running and at least one normal Stable Diffusion/SDXL-style checkpoint is installed in ComfyUI's `models/checkpoints` folder, Shorts Studio detects it and builds the API workflow itself.

You can force a particular checkpoint with:

```bat
set COMFYUI_IMAGE_CHECKPOINT=your-model-file.safetensors
py run.py
```

## AI video

Video models use more specialised ComfyUI graphs. Shorts Studio looks for:

`workflows/video_api.json`

This must be an **API-format** ComfyUI workflow (not the normal UI workflow JSON).

Shorts Studio will replace these exact placeholders wherever they occur in the workflow:

- `__PROMPT__`
- `__NEGATIVE__`
- `__SEED__`
- `__WIDTH__`
- `__HEIGHT__`
- `__FRAMES__`
- `__SECONDS__`

Recommended first target for an 8 GB GPU: a Wan 2.1 T2V 1.3B 480p workflow with CPU/model offloading.

The workflow path can be changed with:

```bat
set COMFYUI_VIDEO_WORKFLOW=C:\path\to\workflow_api.json
py run.py
```

Do not commit model files to this repository.
