#!/usr/bin/env python3
"""
Live Mood Prediction for Smart Dog Collar
Connects to the collar, runs the trained model on the last 8 seconds, and
says the dog's mood as an English phrase through the computer's speakers.

It only speaks when the model is confident; otherwise it prints its best guess.

    python live_predict.py               # collar only
    python live_predict.py --camera 0    # collar + cage camera
    python live_predict.py --hr Polar    # collar + heart-rate chest strap
"""

import argparse
import asyncio
import json
import random
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from collar import (EVENTS, ML_DIR, PHRASES, SAMPLE_WRAP, CollarStream,
                    require_bleak)
from features import HOP, WINDOW, compute_window_features

MODEL_DIR = ML_DIR / "trained_models"
SMOOTH_WINDOWS = 3       # average this many predictions (12 s) before deciding
REPEAT_SECONDS = 60      # say the same mood again only after this long


def speak(text):
    """Say a phrase aloud with the operating system's own voice, without blocking."""
    if sys.platform == "win32":
        script = ("Add-Type -AssemblyName System.Speech; "
                  "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{}')"
                  .format(text.replace("'", "''")))
        command = ["powershell", "-NoProfile", "-Command", script]
    elif sys.platform == "darwin":
        command = ["say", text]
    elif shutil.which("espeak"):
        command = ["espeak", text]
    else:
        return
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class MoodPredictor:
    """Turns a stream of collar rows into smoothed mood decisions."""

    def __init__(self, model, metadata):
        self.model = model
        self.metadata = metadata
        self.rows = deque(maxlen=WINDOW)
        self.since_prediction = 0
        self.last_sample = None
        self.recent = deque(maxlen=SMOOTH_WINDOWS)

    def add_row(self, row):
        """Add one row. Returns (mood, confidence) when a new prediction is ready."""
        # After dropped packets the window would mix two moments, so start over
        if self.last_sample is not None and (row["sample"] - self.last_sample) % SAMPLE_WRAP != 1:
            self.rows.clear()
            self.recent.clear()
        self.last_sample = row["sample"]

        self.rows.append(row)
        self.since_prediction += 1
        if len(self.rows) < WINDOW or self.since_prediction < HOP:
            return None
        self.since_prediction = 0

        features = compute_window_features(pd.DataFrame(self.rows), self.metadata["use_context"])
        X = pd.DataFrame([features])[self.metadata["feature_names"]]
        self.recent.append(self.model.predict_proba(X)[0])
        proba = np.mean(self.recent, axis=0)
        best = int(proba.argmax())
        return self.model.classes_[best], float(proba[best])


class LiveSession:
    def __init__(self, predictor, mute=False, camera=None):
        self.predictor = predictor
        self.threshold = predictor.metadata["confidence_threshold"]
        self.mute = mute
        self.stream = CollarStream(self.on_row, camera=camera)
        self.spoken_mood = None
        self.spoken_time = 0.0

    def on_row(self, row, now):
        result = self.predictor.add_row(row)
        if result is None:
            return
        mood, confidence = result
        stamp = time.strftime("%H:%M:%S", time.localtime(now))

        if confidence < self.threshold:
            print(f"[{stamp}] not sure (best guess: {mood}, {confidence:.0%})")
            return

        print(f"[{stamp}] {mood} ({confidence:.0%})")
        if mood != self.spoken_mood or now - self.spoken_time > REPEAT_SECONDS:
            phrase = random.choice(PHRASES[mood])
            print(f"           \"{phrase}\"")
            if not self.mute:
                speak(phrase)
            self.spoken_mood, self.spoken_time = mood, now

    async def command_loop(self, client):
        print("\n[LIVE] Listening. The first mood appears after about 8 seconds.")
        print("       Events: " + ", ".join(f"'{k}' = {v}" for k, v in EVENTS.items()))
        print("       'q' = quit\n")
        while client.is_connected:
            text = (await asyncio.to_thread(input)).strip().lower()
            if text == "q":
                break
            elif text in EVENTS:
                self.stream.context.log_event(text)


def main():
    parser = argparse.ArgumentParser(description="Say the dog's mood live")
    parser.add_argument("--model-dir", default=MODEL_DIR, help="folder written by train_mood_model.py")
    parser.add_argument("--hr", metavar="NAME",
                        help="also use a BLE heart-rate strap whose name contains NAME, e.g. Polar")
    parser.add_argument("--camera", metavar="SOURCE",
                        help="also use the cage camera: an index such as 0, or a stream URL")
    parser.add_argument("--mute", action="store_true", help="print phrases without speaking them")
    args = parser.parse_args()

    model_file = Path(args.model_dir) / "dog_mood_model.joblib"
    if not model_file.exists():
        print(f"[ERROR] No trained model at {model_file}")
        print("[ERROR] Train one first: python train_mood_model.py")
        return 1
    model = joblib.load(model_file)
    metadata = json.loads((model_file.parent / "model_metadata.json").read_text(encoding="utf-8"))

    print(f"[MODEL] Moods: {', '.join(metadata['classes'])}")
    print(f"[MODEL] Accuracy on held-out sessions: {metadata['held_out_accuracy']:.1%}")
    if metadata["uses_heart_rate"] and not args.hr:
        print("[MODEL] Warning: this model was trained with a heart-rate strap. "
              "Without --hr its guesses will be worse.")

    if metadata.get("uses_camera") and not args.camera:
        print("[MODEL] Warning: this model was trained with the cage camera. "
              "Without --camera its guesses will be worse.")

    require_bleak()
    camera = None
    if args.camera:
        from camera import CameraTracker
        camera = CameraTracker(args.camera).start()

    session = LiveSession(MoodPredictor(model, metadata), mute=args.mute, camera=camera)
    try:
        asyncio.run(session.stream.run(session.command_loop, args.hr))
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Stopped.")
    finally:
        if camera:
            camera.stop()
    return 0


if __name__ == "__main__":
    print("====== Dog Mood Live ======\n")
    raise SystemExit(main())
