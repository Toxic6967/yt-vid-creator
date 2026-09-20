# Shorts Studio V3

Private/local-first **AI-directed Roblox animation studio** for Windows.

The main workflow builds short cinematic Roblox stories aimed at young Roblox players: a strong opening, a recognisable situation, recurring/consistent characters, escalating conflict, a real payoff, character dialogue, generated movie-style scenes, active-word captions, subtle SFX, metadata, and a manual review queue.

**Nothing is auto-published to YouTube.**

## V3 visual direction

Story Studio V3 prefers **controlled Roblox R15 animation** over full-frame AI video generation.

The default path is now:

`GAME RESEARCH → STORY → LOGIC AUDIT → NARRATION → ROBLOX ENVIRONMENT PLATES → ANIMATION SHOT PLAN → FIXED R15 RIGS → BLENDER ACTION/CAMERA/VFX RENDER → CAPTIONS/SFX/MUSIC → REVIEW`

This keeps the characters consistent and prevents frame-to-frame generative morphing. FLUX is still used to create Roblox-looking environment plates; Blender then animates fixed R15-style characters over those environments. The old FLUX→LTX generative path remains available as a legacy fallback.

Story Studio also includes an optional **Powers / animated action** genre. Powers are treated as original fictional abilities in the channel's animated universe, not as claims about the real Roblox game's mechanics. Available reusable effects include energy, dashes, shields, shockwaves, telekinesis, portals and lightning.

The V3 scene/shot architecture is intentionally reusable for a future long-form mode, but 10–15 minute episode generation is not exposed yet.

## Animation engine setup

Run:

```bat
install_animation_engine.bat
```

This checks for Blender and can install it through Windows winget. Restart Shorts Studio afterward.

For the complete Story stack:

```bat
upgrade_story_quality.bat
```

V3 animated Story mode still uses ComfyUI/FLUX for the game-environment plates, so ComfyUI must be available when a Story starts.

## Current creative direction

Story Studio is deliberately not a generic AI-slop generator. Before rendering, the local writer creates several concepts and scores them for hook, relatability, escalation, payoff, dialogue, visual movie potential, character consistency, and cringe avoidance.

Weak stories are rewritten before expensive media generation. Story mode rejects canned morals, babyish wording, forced slang, random shock value, long exposition and generic creator filler.

Typical formats include relatable gameplay pain, horror-game situations, teammate betrayal, rare-item luck, obbies, server mysteries, survival rounds, funny reversals and satisfying wins.

## Story pipeline

`IDEAS → COMMISSIONING SCORE → CAUSAL SCREENPLAY → LOGIC AUDIT → SHOT PLAN → CONTINUOUS NARRATION → ENVIRONMENT PLATES → CONTROLLED R15 ANIMATION → ACTIVE CAPTIONS → SFX/MUSIC → EDIT → QUALITY GATE → REVIEW`

Story scenes carry exact character descriptions (hair, clothing, colours and personality), environment, action, camera, emotion, motion priority and dialogue speaker.

For continuity, later SDXL keyframes can use the previous keyframe as an img2img reference. The stronger video path animates generated keyframes rather than asking a text-to-video model to invent the character and scene from scratch.

## Stack

- FastAPI dashboard: `127.0.0.1:8765`
- SQLite queue/history
- Ollama + `qwen3:8b` for local story planning/writing/scoring
- ComfyUI for images and video
- SDXL for cinematic keyframes
- Blender/Eevee for deterministic R15-style character animation, reusable motion, cameras and power VFX
- FLUX.2 Klein for Roblox game-environment plates and legacy generative Story imagery
- Optional LTX 2B FP8 keyframe-to-video backend for legacy Story mode
- Wan 2.1 retained for standalone/legacy video tools
- Chatterbox for continuous Story narration, with Kokoro retained for legacy/fallback tools
- FFmpeg through `imageio-ffmpeg`
- ASS captions using actual TTS word timings
- locally generated procedural SFX for whoosh/impact/alert/glitch/reward cues

## Windows setup

From the repository:

```bat
setup_windows.bat
ollama pull qwen3:8b
```

Start ComfyUI, then:

```bat
py run.py
```

Open `http://127.0.0.1:8765`.

## Cinematic Story video backend

For the higher-quality Story mode, run:

```bat
install_story_video_models.bat
```

The installer finds the real Comfy Desktop backend/model folder and installs the local LTX story-video files. These are large downloads.

After installation:

1. Completely close ComfyUI.
2. Reopen ComfyUI.
3. Restart Shorts Studio with `py run.py`.
4. Open Video Studio and check the engine status.

When detected, the UI reports:

`ComfyUI connected • cinematic keyframe→video engine ready (LTX 2B FP8)`

The RTX 3060 Ti 8GB is at the low end for this backend, so generation can be slow and memory-sensitive. Shorts Studio unloads Qwen before ComfyUI media generation to avoid both systems competing for VRAM.

## Story quality rules

A Story-mode export is not considered finished simply because an MP4 exists. The quality gate requires a passing story/retention score, no placeholder storyboard visuals, appropriate runtime, a real output file, and several completed cinematic keyframe-to-video shots.

If the cinematic backend is unavailable or too few quality motion shots finish, Story mode stops instead of silently substituting the old low-quality text-to-video look.

## Captions

Story captions use real word-boundary timing, short 2–4 word chunks, currently-spoken-word highlighting, word pop/scale animation, stronger hook/reveal/payoff treatment, compact two-line layouts, and placement intended to avoid character faces.

## Audio

Story characters can receive separate neural voices. Character dialogue uses gentler rate/pitch settings than the narrator so it sounds more conversational.

Put licensed music in `data/assets/music/` if you want background music. Built-in original procedural SFX are generated locally for supported scene cues, so the app does not need to scrape copyrighted sound packs.

## Outputs

Each job is stored under `data/outputs/<job-id>/`. A successful job includes `final.mp4` and `manifest.json`, with story, characters, shot plan, generation details and quality checks.

## Privacy / costs

- Local dashboard only.
- Ollama inference is local.
- ComfyUI generation is local.
- No OpenAI, Anthropic, ElevenLabs or Runway API is required.
- Edge TTS and web discovery still require internet access.
- No automatic YouTube publishing.

## Development sanity check

```bat
py -m compileall shorts_studio run.py
```

## Troubleshooting

If the dashboard says Ollama is unavailable, test `ollama list`.

If Story mode says the cinematic backend is missing, run `install_story_video_models.bat`, then restart ComfyUI and Shorts Studio.

If a Story job fails its quality gate, check the Review Queue/manifest. The app is intentionally designed to reject weak media instead of calling it upload-ready.
