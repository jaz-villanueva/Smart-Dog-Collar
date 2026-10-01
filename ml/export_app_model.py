#!/usr/bin/env python3
"""
Export a trained mood model for the TinyTalk web app.

The app runs in a phone browser, which cannot load a scikit-learn model, so
this writes the Random Forest's trees as JSON for app/core.js to walk.

    python export_app_model.py                                   # your model, from trained_models/
    python export_app_model.py --model-dir starter_model --synthetic

With --sample it also writes app/test/parity_sample.json: a few windows with
the features and probabilities Python computes for them, which
`node app/check_parity.mjs` compares against the app's own arithmetic.
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from collar import BAND_COLUMNS, BEACON_COLUMNS, ML_DIR, PHRASES
from features import WINDOW, compute_window_features

APP_DIR = ML_DIR.parent / "app"
SAMPLE_WINDOWS = 4


def export_tree(estimator):
    tree = estimator.tree_
    value = tree.value[:, 0, :]
    value = value / value.sum(axis=1, keepdims=True)
    return {
        "left": tree.children_left.tolist(),      # -1 marks a leaf
        "right": tree.children_right.tolist(),
        "feature": tree.feature.tolist(),
        "threshold": tree.threshold.tolist(),
        "value": [[round(float(p), 5) for p in row] if left == -1 else 0
                  for row, left in zip(value, tree.children_left)],
    }


def blank_to_none(value):
    return None if pd.isna(value) else float(value)


def export_sample(model, metadata, data_file):
    """A few windows as the app would see them, with Python's answers."""
    df = pd.read_csv(data_file, dtype={"session_id": str})
    sessions = [s for _, s in df.groupby("session_id", sort=False) if len(s) >= WINDOW]
    step = max(1, len(sessions) // SAMPLE_WINDOWS)
    windows = []
    for session in sessions[::step][:SAMPLE_WINDOWS]:
        window = session.iloc[:WINDOW]
        features = compute_window_features(window, metadata["use_context"])
        X = pd.DataFrame([features])[metadata["feature_names"]]
        packets = []
        for i in range(0, WINDOW, 2):
            first, pair = window.iloc[i], window.iloc[i:i + 2]
            packets.append({
                "seq": int(first["sample"]) // 2,
                "motion": pair[["accel_x", "accel_y", "accel_z",
                                "gyro_x", "gyro_y", "gyro_z"]].to_numpy(dtype=float).tolist(),
                "rms": float(first["audio_rms"]),
                "domHz": float(first["dom_freq_hz"]),
                "zcr": float(first["zcr"]),
                "bands": [float(first[c]) for c in BAND_COLUMNS],
                "rssi": [blank_to_none(first[c]) for c in BEACON_COLUMNS],
            })
        last = window.iloc[-1]
        windows.append({
            "mood": str(last["mood"]),
            "packets": packets,
            "context": {
                "hour": blank_to_none(last["hour"]),
                "minsSinceFed": blank_to_none(last["mins_since_fed"]),
                "minsSincePotty": blank_to_none(last["mins_since_potty"]),
                "ownerAway": bool(last["owner_away"]),
            },
            "features": {k: float(v) for k, v in features.items()},
            "proba": model.predict_proba(X)[0].tolist(),
        })
    return windows


def main():
    parser = argparse.ArgumentParser(description="Export a mood model for the web app")
    parser.add_argument("--model-dir", default=ML_DIR / "trained_models",
                        help="folder written by train_mood_model.py")
    parser.add_argument("--synthetic", action="store_true",
                        help="mark the model as trained on synthetic data; the app then warns the user")
    parser.add_argument("--sample", metavar="CSV",
                        help="also write parity test windows taken from this recording")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    model = joblib.load(model_dir / "dog_mood_model.joblib")
    metadata = json.loads((model_dir / "model_metadata.json").read_text(encoding="utf-8"))
    if metadata["uses_heart_rate"] or metadata.get("uses_camera"):
        print("[EXPORT] Warning: this model was trained with a heart-rate strap or camera, "
              "which the app does not have. Its guesses in the app will be worse.")

    exported = {
        "classes": [str(c) for c in model.classes_],
        "feature_names": metadata["feature_names"],
        "confidence_threshold": metadata["confidence_threshold"],
        "held_out_accuracy": metadata["held_out_accuracy"],
        "synthetic": args.synthetic,
        "phrases": PHRASES,
        "trees": [export_tree(e) for e in model.estimators_],
    }
    model_file = APP_DIR / "model.json"
    model_file.write_text(json.dumps(exported, separators=(",", ":")), encoding="utf-8")
    print(f"[EXPORT] {len(exported['trees'])} trees written to {model_file} "
          f"({model_file.stat().st_size / 1e6:.1f} MB)")

    if args.sample:
        sample_file = APP_DIR / "test" / "parity_sample.json"
        sample_file.parent.mkdir(exist_ok=True)
        sample_file.write_text(json.dumps(export_sample(model, metadata, args.sample),
                                          separators=(",", ":")), encoding="utf-8")
        print(f"[EXPORT] Parity windows written to {sample_file}")


if __name__ == "__main__":
    main()
