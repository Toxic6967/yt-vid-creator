# Shorts Studio V1

Private/local-first YouTube Shorts generation workstation for Windows. It researches a topic, creates an original source-grounded script with a local LLM, generates narration, gathers reusable Wikimedia Commons visuals (or creates procedural visuals), edits a 1080x1920 Short with animated captions, produces metadata, and places the result into a manual review queue.

**V1 never auto-publishes to YouTube.**

## Why this build is intentionally not a spam bot

Shorts Studio stores its research sources, scene-level source IDs, external visual attribution, and quality checks in a manifest beside every export. It refuses to proceed when it cannot find at least two independent sources. The goal is a creator-assist workflow where you review the result before publishing.

## Stack

- FastAPI local dashboard on `127.0.0.1:8765`
- SQLite job/review queue
- Ollama + `qwen3:8b` for local topic selection, scripting, fact-check assistance, and metadata
- DDGS for free web discovery
- Wikimedia Commons API for reusable visual assets and attribution metadata
- Procedural original visuals as a fallback
- Edge TTS for no-key narration (internet connection required)
- FFmpeg supplied through `imageio-ffmpeg` for the final edit
- ASS animated captions generated from TTS word timings

## Windows setup

### 1. Clone the repository

```bat
git clone https://github.com/Toxic6967/yt-vid-creator.git
cd yt-vid-creator
```

### 2. Install Python dependencies

You can double-click `setup_windows.bat`, or run:

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
pip install -r requirements.txt
```

Python 3.13 is supported by the main dependencies used here.

### 3. Install Ollama and the local model

Install Ollama for Windows, then in Command Prompt:

```bat
ollama pull qwen3:8b
```

Keep Ollama running. The app talks only to the local Ollama endpoint by default: `http://127.0.0.1:11434`.

### 4. Start Shorts Studio

```bat
py run.py
```

It opens:

`http://127.0.0.1:8765`

## First run

1. Enter a channel name and niche.
2. Leave Topic blank if you want automatic topic discovery.
3. Choose a voice and a 20-45 second target length.
4. Click **GENERATE SHORT**.
5. Watch the job progress in the review queue.
6. Review the MP4, sources, rights manifest, title, description, and hashtags.
7. Click Approve or Regenerate.

Exports are stored under:

`data/outputs/<job-id>/`

Each job includes `final.mp4` and `manifest.json`.

## Music and SFX

To keep licensing under your control, V1 does **not** scrape random music. Put music you own or are licensed to monetize in:

`data/assets/music/`

If a supported file is present, Shorts Studio mixes one track quietly under narration. If the folder is empty, it exports narration without background music.

The `data/assets/sfx/` folder is reserved for the next pass of sound-design automation.

## Local model choices

Default:

```bat
ollama pull qwen3:8b
```

Change the model with an environment variable:

```bat
set SHORTS_STUDIO_MODEL=qwen3:4b
py run.py
```

The 8B Q4 model is the recommended quality/speed starting point for an RTX 3060 Ti 8GB. The 4B model uses less VRAM if needed.

## Privacy / keys

- Dashboard binds to `127.0.0.1`, not your LAN.
- No OpenAI, Anthropic, ElevenLabs, Runway, or paid API key is required.
- Do not commit secrets into this repository.
- Edge TTS and web research require internet access.
- Research queries and TTS text therefore leave your PC to those respective services; the local LLM inference itself stays on your machine.

## V1 limitations / next upgrades

V1 is deliberately conservative. It uses still images with camera motion instead of ripping copyrighted clips. Strong next upgrades are:

- optional local ComfyUI image/video generation backend
- better per-word caption highlighting and design presets
- local Piper/Kokoro narration backend for fully local TTS
- optional Pexels/Pixabay providers with explicit API keys and license logs
- YouTube analytics import for learning what hooks/topics work
- niche/channel profiles and reusable visual styles
- thumbnail/cover-frame designer
- manual YouTube upload helper after review (still no automatic publishing by default)

## Troubleshooting

**Dashboard says Ollama not running**

Open Ollama, then test:

```bat
ollama list
```

**Dashboard says model is missing**

```bat
ollama pull qwen3:8b
```

**A job fails during narration**

Edge TTS needs internet access. Regenerate after connectivity is restored.

**A job says Review needed**

Open its manifest. The quality gate will show whether the issue was duration, source count, source citations, rights metadata, or the final output file.
