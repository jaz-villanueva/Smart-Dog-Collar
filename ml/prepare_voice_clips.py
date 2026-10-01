#!/usr/bin/env python3
"""
Turn clips recorded elsewhere into the sound clips the TinyTalk app plays.

Use this when the phrases were spoken by a voice service in the browser
(the current ones come from Fish Audio) rather than by make_voice_clips.py.
Save each phrase as <mood>_<n>.mp3 or .wav in one folder, named after its
place in moods.json: playful_1 is the first playful phrase, and so on. The
out-of-range alarm is lost_1. Then:

    pip install soundfile scipy
    python prepare_voice_clips.py my_clips --pitch 1.08

For each phrase it trims the silence at both ends, evens out the loudness,
and optionally raises the pitch. Raising the pitch by a factor also makes the
clip that much shorter, so 1.08 is 8% higher and 8% quicker.

It writes app/voice/<mood>_<n>.wav and app/voice/index.json.
"""

import argparse
import json
from fractions import Fraction
from pathlib import Path

import numpy as np

from make_voice_clips import EXTRA, VOICE_DIR
from collar import PHRASES

OUT_RATE = 24000      # plenty for speech, and keeps the clips small
QUIET = 0.02          # below this the clip is treated as silence
PAD_SECONDS = 0.05    # silence kept at each end
PEAK = 0.9


def prepare(path, pitch):
    import soundfile as sf
    from scipy.signal import resample_poly

    samples, rate = sf.read(path)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    loud = np.flatnonzero(np.abs(samples) > QUIET * np.abs(samples).max())
    pad = int(PAD_SECONDS * rate)
    samples = samples[max(0, loud[0] - pad):loud[-1] + pad]

    # Playing the samples back faster raises the pitch and shortens the clip
    ratio = Fraction(OUT_RATE / (rate * pitch)).limit_denominator(5000)
    samples = resample_poly(samples, ratio.numerator, ratio.denominator)
    return samples * (PEAK / np.abs(samples).max())


def main():
    parser = argparse.ArgumentParser(description="Prepare recorded phrases for the app")
    parser.add_argument("folder", help="folder holding <mood>_<n>.mp3 or .wav for every phrase")
    parser.add_argument("--pitch", type=float, default=1.0,
                        help="raise the pitch, and the speed, by this factor (default 1.0)")
    args = parser.parse_args()

    import soundfile as sf
    folder = Path(args.folder)
    wanted = {f"{mood}_{n}": phrase for mood, phrases in {**PHRASES, **EXTRA}.items()
              for n, phrase in enumerate(phrases, start=1)}
    found = {name: next((folder / f"{name}{ext}" for ext in (".mp3", ".wav")
                         if (folder / f"{name}{ext}").exists()), None) for name in wanted}
    missing = [name for name, path in found.items() if path is None]
    if missing:
        print(f"[VOICE] Missing from {folder}: {', '.join(missing)}")
        return 1

    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    for old in VOICE_DIR.glob("*.wav"):
        old.unlink()

    index, seconds = {}, 0.0
    for name, phrase in wanted.items():
        samples = prepare(found[name], args.pitch)
        sf.write(VOICE_DIR / f"{name}.wav", samples, OUT_RATE, subtype="PCM_16")
        seconds += len(samples) / OUT_RATE
        index[phrase] = f"{name}.wav"
        print(f"[VOICE] {name + '.wav':16s} {len(samples) / OUT_RATE:4.2f} s  {phrase}")

    (VOICE_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    size = sum(f.stat().st_size for f in VOICE_DIR.glob("*.wav"))
    print(f"[VOICE] {len(index)} clips, {seconds:.0f} s, {size / 1e6:.1f} MB, pitch x{args.pitch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
