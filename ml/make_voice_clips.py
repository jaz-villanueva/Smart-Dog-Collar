#!/usr/bin/env python3
"""
Record every phrase in moods.json as a sound clip for the TinyTalk app.

The clips are made on your computer by Piper, a free open-source speech
engine, so there is no account, no fee and no limit. Run this again whenever
you change a phrase in moods.json.

    pip install piper-tts
    python -m piper.download_voices en_US-joe-medium
    python make_voice_clips.py --voice en_US-joe-medium.onnx

It writes app/voice/<mood>_<n>.wav and app/voice/index.json, which tells the
app which clip belongs to which phrase. See app/voice/README.md for the
voice's licence.
"""

import argparse
import json
import wave
from pathlib import Path

from collar import ML_DIR, PHRASES

VOICE_DIR = ML_DIR.parent / "app" / "voice"
# Said by the app itself, not by the dog
EXTRA = {"lost": ["I can't hear the collar."]}


def main():
    parser = argparse.ArgumentParser(description="Record the phrases as sound clips")
    parser.add_argument("--voice", required=True, help="path to a Piper voice (.onnx file)")
    args = parser.parse_args()

    from piper import PiperVoice
    voice = PiperVoice.load(args.voice)

    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    for old in VOICE_DIR.glob("*.wav"):
        old.unlink()

    index, seconds = {}, 0.0
    for mood, phrases in {**PHRASES, **EXTRA}.items():
        for number, phrase in enumerate(phrases, start=1):
            name = f"{mood}_{number}.wav"
            with wave.open(str(VOICE_DIR / name), "wb") as clip:
                voice.synthesize_wav(phrase, clip)
            with wave.open(str(VOICE_DIR / name), "rb") as clip:
                seconds += clip.getnframes() / clip.getframerate()
            index[phrase] = name
            print(f"[VOICE] {name:16s} {phrase}")

    (VOICE_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    size = sum(f.stat().st_size for f in VOICE_DIR.glob("*.wav"))
    print(f"[VOICE] {len(index)} clips, {seconds:.0f} s, {size / 1e6:.1f} MB, voice {Path(args.voice).stem}")


if __name__ == "__main__":
    main()
