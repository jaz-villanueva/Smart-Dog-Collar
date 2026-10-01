#!/usr/bin/env python3
"""
Record every phrase in moods.json as a sound clip for the TinyTalk app.

The clips are made on your computer by Piper, a free open-source speech
engine, so there is no account, no fee and no limit. Run this again whenever
you change a phrase in moods.json.

    pip install piper-tts
    python -m piper.download_voices en_US-ljspeech-medium
    python make_voice_clips.py --voice en_US-ljspeech-medium.onnx --pitch 1.3

--pitch raises the voice: 1.0 is the voice as recorded, 1.3 is small and
puppy-like. The phrase is spoken slower by that factor and then played back
faster by the same factor, so it ends up higher but no quicker.

It writes app/voice/<mood>_<n>.wav and app/voice/index.json, which tells the
app which clip belongs to which phrase. See app/voice/README.md for the
voice's licence.
"""

import argparse
import io
import json
import wave
from pathlib import Path

import numpy as np

from collar import ML_DIR, PHRASES

VOICE_DIR = ML_DIR.parent / "app" / "voice"
# Said by the app itself, not by the dog
EXTRA = {"lost": ["I can't hear the collar."]}


def speak(voice, phrase, pitch):
    """One phrase as 16-bit samples at the voice's own sample rate, raised by pitch."""
    from piper.config import SynthesisConfig
    slow = SynthesisConfig(length_scale=(voice.config.length_scale or 1.0) * pitch)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        voice.synthesize_wav(phrase, clip, syn_config=slow)
    buffer.seek(0)
    with wave.open(buffer, "rb") as clip:
        rate = clip.getframerate()
        samples = np.frombuffer(clip.readframes(clip.getnframes()), dtype=np.int16).astype(float)
    # Squeeze the slow recording back to normal length, which raises its pitch
    positions = np.arange(0, len(samples) - 1, pitch)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.int16), rate


def main():
    parser = argparse.ArgumentParser(description="Record the phrases as sound clips")
    parser.add_argument("--voice", required=True, help="path to a Piper voice (.onnx file)")
    parser.add_argument("--pitch", type=float, default=1.0,
                        help="how much higher than the voice as recorded (default 1.0; 1.3 is puppy-like)")
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
            samples, rate = speak(voice, phrase, args.pitch)
            with wave.open(str(VOICE_DIR / name), "wb") as clip:
                clip.setnchannels(1)
                clip.setsampwidth(2)
                clip.setframerate(rate)
                clip.writeframes(samples.tobytes())
            seconds += len(samples) / rate
            index[phrase] = name
            print(f"[VOICE] {name:16s} {phrase}")

    (VOICE_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    size = sum(f.stat().st_size for f in VOICE_DIR.glob("*.wav"))
    print(f"[VOICE] {len(index)} clips, {seconds:.0f} s, {size / 1e6:.1f} MB, voice {Path(args.voice).stem}, "
          f"pitch x{args.pitch}")


if __name__ == "__main__":
    main()
