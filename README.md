# Shorts Studio V5

Private/local-first **automatic Roblox YouTube Shorts studio** for Windows.

The default workflow is now built around **real Roblox experiences** instead of a generic original world. Full Auto can choose a recognisable Roblox game, research its real mechanics and locations, write a short story around things players actually do, narrate it, build game-specific environment plates, animate consistent Roblox-style characters in Blender, add captions/SFX/music, and place the result in a manual review queue.

**Nothing is auto-published to YouTube.**

## V5 direction

The target is short Roblox machinima: readable characters, clear physical actions, familiar game situations, fast camera language and a payoff that makes sense.

Default flow:

`REAL GAME DISCOVERY → GAME RESEARCH → STORY → LOGIC AUDIT → NARRATION → GAME-SPECIFIC ENVIRONMENT PLATES → SHOT/BLOCKING PLAN → BLENDER ROBLOX MACHINIMA → CAPTIONS/SFX/MUSIC → QUALITY GATE → REVIEW`

Real-game Story mode is now the recommended/default mode. The older original Max/Mia/Kai animated universe remains available as an optional Story world.

Typical real-game formats include DOORS-style survival/horror situations, teammate betrayal, rare-item luck, obbies, round-based games, server mysteries, funny reversals and satisfying wins. The writer is instructed not to invent mechanics that the research did not establish.

## Why V5 changed the renderer

The previous renderer depended too heavily on importing one R15 FBX correctly and then placing it over a mostly flat AI background. A bad import or weak rig could make the avatar look like detached blocks/spheres even when the rest of the pipeline worked.

V5 instead builds a deterministic segmented Roblox-style avatar directly in Blender:

- separate upper/lower torso, upper/lower arms and legs, hands and feet
- classic readable face and hair silhouette
- proper floor/ground contact and shadow
- reusable shoulder/elbow/hip/knee pivots
- walk/run/dash cycles, jumps, crouches, reactions, pointing, pickups, buttons/doors, falls and celebrations
- reusable power VFX for the optional original fantasy mode
- game-action props such as doors, keys, buttons, chests and collectibles when the screenplay establishes them
- vertical camera presets plus push, track, follow, orbit and reveal motion
- foreground floor/depth geometry so the result reads as a 3D scene instead of a character pasted onto a slideshow

The official Roblox BlockyCharacter FBX is now only an optional legacy/reference asset. V5 rendering does not fail just because that FBX is absent or imports differently in a newer Blender version.

## Environment plates

ComfyUI/FLUX is still used for the researched Roblox environment plate.

V5 prompts the plate generator to produce:

- a recognisable verified game location/set-piece
- a player-height perspective
- a coherent horizon and depth
- one clear solid foreground floor for the animated characters
- uncluttered foreground staging space
- no accidental humanoids, floating blobs, unrelated vehicles, readable text or UI

Blender then supplies the consistent characters, physical actions, props, lighting, camera motion and effects.

## Setup

From the repository:

```bat
setup_windows.bat
ollama pull qwen3:8b
install_animation_engine.bat
upgrade_story_quality.bat
```

Start ComfyUI, then:

```bat
py run.py
```

Open:

`http://127.0.0.1:8765`

The animation installer checks/installs Blender. The old Roblox FBX download is best-effort only and does not block V5.

## Recommended Story settings

In Video Studio → Story:

- **Story world:** Real Roblox game story
- **Story genre:** Auto
- **Target:** about 58 seconds
- **Visual mode:** Animated / V5 machinima
- **Game/story idea:** leave blank to let Full Auto choose, or enter a game such as DOORS, Dandy's World, Murder Mystery 2 or 99 Nights in the Forest

The actual available game is still validated through the research stage; a named game is not treated as permission to invent unsupported mechanics.

## Stack

- FastAPI dashboard: `127.0.0.1:8765`
- SQLite queue/history
- Ollama + `qwen3:8b` for local planning/writing/scoring
- web discovery/research for real Roblox game context
- ComfyUI + FLUX.2 Klein for Roblox environment plates
- Blender/Eevee for deterministic Roblox machinima characters, actions, props, cameras and VFX
- Chatterbox for continuous Story narration
- FFmpeg through `imageio-ffmpeg`
- ASS active-word captions using narration timing
- procedural/local SFX support
- optional LTX keyframe-to-video legacy/generative fallback

## Quality gates

An MP4 existing does not mean a Story passes.

Story mode checks screenplay/retention quality, causal logic, duration, environment variety, completed animated shots, clip decodability, visible motion where motion is expected, and output existence. Weak stories or broken scene renders should stop or enter review rather than silently being called upload-ready.

## Outputs

Each job is stored under:

`data/outputs/<job-id>/`

A completed job includes `final.mp4` and `manifest.json`. V5 animation also stores the shot plan and per-scene render reports while building the Short.

## Development sanity check

```bat
py -m compileall shorts_studio scripts/blender run.py
```

GitHub pull requests also run the Python sanity workflow.

## Troubleshooting

If Ollama is unavailable, test `ollama list`.

If animated Story mode says Blender is missing, run `install_animation_engine.bat` and restart Shorts Studio.

If ComfyUI environment generation is unavailable, start ComfyUI and run `upgrade_story_quality.bat` if the Story image models are missing.

If a Story fails the quality gate, open its Review/manifest information before regenerating. V5 is intentionally stricter about broken animation and unrelated game visuals.
