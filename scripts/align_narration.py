from __future__ import annotations

import argparse
import json
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()

    model = WhisperModel(
        "tiny.en",
        device="cpu",
        compute_type="int8",
        download_root=args.model_dir,
    )
    segments, _ = model.transcribe(
        args.audio,
        language="en",
        beam_size=1,
        word_timestamps=True,
        vad_filter=False,
        condition_on_previous_text=False,
    )

    words = []
    for segment in segments:
        for word in segment.words or []:
            text = str(word.word or "").strip()
            if not text:
                continue
            start = float(word.start or 0.0)
            end = float(word.end or start)
            words.append(
                {
                    "text": text,
                    "start": start,
                    "duration": max(0.04, end - start),
                }
            )

    Path(args.output).write_text(
        json.dumps({"words": words}, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
