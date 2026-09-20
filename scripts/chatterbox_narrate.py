from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
import torchaudio as ta
import perth

# On some Windows installs resemble-perth imports successfully but its optional
# neural watermarker fails to import, leaving PerthImplicitWatermarker = None.
# Chatterbox constructs that class unconditionally and crashes before synthesis.
# Perth ships an official DummyWatermarker for exactly this kind of fallback.
# Use it only when the real implementation is unavailable; speech generation is
# otherwise unchanged.
if getattr(perth, "PerthImplicitWatermarker", None) is None:
    perth.PerthImplicitWatermarker = perth.DummyWatermarker

from chatterbox.tts import ChatterboxTTS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--exaggeration", type=float, default=0.46)
    parser.add_argument("--cfg-weight", type=float, default=0.34)
    parser.add_argument("--temperature", type=float, default=0.72)
    args = parser.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("Narration text is empty.")

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    def synthesize(target_device: str):
        model = ChatterboxTTS.from_pretrained(device=target_device)
        wav = model.generate(
            text,
            exaggeration=args.exaggeration,
            cfg_weight=args.cfg_weight,
            temperature=args.temperature,
            repetition_penalty=1.15,
            min_p=0.06,
            top_p=0.95,
        )
        return model, wav

    try:
        model, wav = synthesize(device)
    except Exception:
        if device != "cuda":
            raise
        # An 8 GB GPU can occasionally be too fragmented even after unloading
        # the image/video stack. Retry on CPU rather than killing the Story.
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        model, wav = synthesize("cpu")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ta.save(str(output), wav.cpu(), model.sr)


if __name__ == "__main__":
    main()
