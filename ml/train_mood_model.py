#!/usr/bin/env python3
"""
Random Forest Mood Detection Model
Trains on collar data recorded and labelled with ble_data_logger.py.

The mood labels you typed are the ground truth. Accuracy is measured on whole
recording sessions the model never saw, because windows cut from the same
session look alike and would make the score look better than it is.
"""

import argparse
import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score,
                             classification_report, f1_score)
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict

from collar import DATA_DIR, ML_DIR, MOODS, SAMPLE_WRAP
from features import (HOP, MISSING, SAMPLE_HZ, WINDOW, WINDOW_SECONDS,
                      compute_window_features)

DATA_FILE = DATA_DIR / "sensor_readings.csv"
RECORDINGS_DIR = DATA_DIR / "recordings"
PHONE_DIR = DATA_DIR / "phone"
OUTPUT_DIR = ML_DIR / "trained_models"

MAX_GAP_SAMPLES = 10  # a longer run of dropped samples splits the recording
MIN_SESSIONS = 2      # per mood, to be able to test on an unseen session
CONFIDENCE = 0.5      # below this, the live script says "not sure" instead of guessing


class MoodModelTrainer:
    def __init__(self, data_file, output_dir, use_context=True, include_recordings=True):
        self.data_file = Path(data_file)
        self.include_recordings = include_recordings
        self.output_dir = Path(output_dir)
        self.use_context = use_context
        self.df = None
        self.model = None
        self.feature_names = None

    def load_data(self):
        """Load sensor data from CSV"""
        print("[DATA] Loading sensor readings...")

        # Live-labelled data, every recording labelled from video, and
        # recordings saved from the TinyTalk app on the phone
        files = [self.data_file] if self.data_file.exists() else []
        if self.include_recordings:
            files += sorted(RECORDINGS_DIR.glob("*/labelled.csv"))
            files += sorted(PHONE_DIR.glob("*.csv"))
        if not files:
            print(f"[ERROR] Data file not found: {self.data_file}")
            print("[ERROR] Run data logger first: python ble_data_logger.py")
            return False
        for file in files:
            print(f"[DATA]   {file}")

        self.df = pd.concat([pd.read_csv(f, dtype={"session_id": str}) for f in files],
                            ignore_index=True)
        self.df = self.df[self.df["mood"].isin(MOODS)]
        print(f"[DATA] Loaded {len(self.df)} labelled samples "
              f"({len(self.df) / SAMPLE_HZ / 60:.1f} minutes)")

        summary = self.df.groupby("mood").agg(
            sessions=("session_id", "nunique"),
            minutes=("sample", lambda s: round(len(s) / SAMPLE_HZ / 60, 1)),
        )
        print("[DATA] Per mood:")
        print(summary.to_string())
        return len(self.df) > 0

    def extract_features(self):
        """Cut each session into overlapping windows and compute features"""
        print(f"\n[FEATURES] Extracting {WINDOW_SECONDS}-second windows...")

        rows, labels, groups = [], [], []
        for session_id, session_df in self.df.groupby("session_id", sort=False):
            mood = session_df["mood"].iloc[0]

            # Never let a window span a break in the recording
            gap = session_df["sample"].diff().fillna(1).mod(SAMPLE_WRAP)
            for _, run in session_df.groupby((gap > MAX_GAP_SAMPLES).cumsum()):
                for start in range(0, len(run) - WINDOW + 1, HOP):
                    window = run.iloc[start:start + WINDOW]
                    rows.append(compute_window_features(window, self.use_context))
                    labels.append(mood)
                    groups.append(session_id)

        features_df = pd.DataFrame(rows)
        self.feature_names = features_df.columns.tolist()
        print(f"[FEATURES] Extracted {len(features_df)} windows, "
              f"{len(self.feature_names)} features each")
        return features_df, np.array(labels), np.array(groups)

    def drop_thin_moods(self, X, y, groups):
        """Keep only moods recorded in enough separate sessions to test honestly"""
        sessions = pd.Series(groups).groupby(y).nunique()
        thin = sessions[sessions < MIN_SESSIONS]
        for mood, count in thin.items():
            print(f"[DATA] Skipping '{mood}': {count} session(s), need {MIN_SESSIONS}+")
        keep = ~np.isin(y, thin.index)
        return X[keep].reset_index(drop=True), y[keep], groups[keep]

    def new_model(self):
        return RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced",  # Handle class imbalance
        )

    def evaluate(self, X, y, groups):
        """Score the model on sessions held out of training"""
        print("\n[EVAL] Testing on held-out sessions...")

        classes = np.unique(y)
        n_splits = min(5, pd.Series(groups).groupby(y).nunique().min())
        folds = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
        proba = cross_val_predict(self.new_model(), X, y, groups=groups, cv=folds,
                                  method="predict_proba")
        y_pred = classes[proba.argmax(axis=1)]

        accuracy = accuracy_score(y, y_pred)
        baseline = pd.Series(y).value_counts(normalize=True).max()
        print(f"[EVAL] Accuracy:  {accuracy:.1%}  "
              f"(always guessing the most common mood scores {baseline:.1%})")
        print(f"[EVAL] Macro F1:  {f1_score(y, y_pred, average='macro'):.2f}")

        # The live script stays silent when unsure; this is how often it speaks, and how well
        sure = proba.max(axis=1) >= CONFIDENCE
        sure_accuracy = accuracy_score(y[sure], y_pred[sure]) if sure.any() else 0.0
        print(f"[EVAL] When at least {CONFIDENCE:.0%} confident: speaks {sure.mean():.1%} "
              f"of the time, right {sure_accuracy:.1%} of those times")

        print("\n[CLASSIFICATION REPORT]")
        print(classification_report(y, y_pred, labels=classes, zero_division=0))

        display = ConfusionMatrixDisplay.from_predictions(
            y, y_pred, labels=classes, xticks_rotation=45, cmap="Blues"
        )
        display.ax_.set_title("Mood Classification on Held-Out Sessions")
        display.figure_.tight_layout()
        plot_file = self.output_dir / "confusion_matrix.png"
        display.figure_.savefig(plot_file, dpi=150)
        plt.close(display.figure_)
        print(f"[PLOT] Confusion matrix saved to {plot_file}")
        return {
            "held_out_accuracy": round(float(accuracy), 4),
            "confident_accuracy": round(float(sure_accuracy), 4),
            "confident_share": round(float(sure.mean()), 4),
        }

    def train_final_model(self, X, y):
        """Fit on every window for the model the live script will use"""
        print("\n[TRAIN] Training final model on all sessions...")
        self.model = self.new_model().fit(X, y)

        ranked = sorted(zip(self.model.feature_importances_, self.feature_names), reverse=True)
        print("[TRAIN] Most useful features:")
        for importance, name in ranked[:10]:
            print(f"         {name:22s} {importance:.3f}")

    def save_model(self, X, scores):
        """Save trained model and the details live_predict.py needs to use it"""
        model_file = self.output_dir / "dog_mood_model.joblib"
        joblib.dump(self.model, model_file)

        metadata = {
            "classes": list(self.model.classes_),
            "feature_names": self.feature_names,
            "use_context": self.use_context,
            "uses_heart_rate": bool((X["hr_mean"] != MISSING).any()),
            "uses_camera": bool((X["cam_x"] != MISSING).any()),
            "confidence_threshold": CONFIDENCE,
            **scores,
        }
        metadata_file = self.output_dir / "model_metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"\n[SAVE] Model saved to {model_file}")
        print(f"[SAVE] Metadata saved to {metadata_file}")


def main():
    parser = argparse.ArgumentParser(description="Train the dog mood classifier")
    parser.add_argument("--data", default=None,
                        help="train on this CSV only (default: all live-labelled and "
                             "video-labelled data)")
    parser.add_argument("--out", default=OUTPUT_DIR, help="folder for the model and plots")
    parser.add_argument("--no-context", action="store_true",
                        help="ignore time of day, feeding, potty and owner-away columns")
    args = parser.parse_args()

    trainer = MoodModelTrainer(args.data or DATA_FILE, args.out,
                               use_context=not args.no_context,
                               include_recordings=args.data is None)

    if not trainer.load_data():
        return 1

    X, y, groups = trainer.extract_features()
    if len(X) == 0:
        print(f"\n[ERROR] No session is longer than {WINDOW_SECONDS} seconds")
        return 1

    X, y, groups = trainer.drop_thin_moods(X, y, groups)
    if len(set(y)) < 2:
        print(f"\n[ERROR] Need at least 2 moods with {MIN_SESSIONS}+ sessions each")
        print("[ERROR] Record each mood on several separate occasions and try again")
        return 1

    trainer.output_dir.mkdir(parents=True, exist_ok=True)
    scores = trainer.evaluate(X, y, groups)
    trainer.train_final_model(X, y)
    trainer.save_model(X, scores)

    print("\n" + "=" * 50)
    print("Model training complete! Try it live: python live_predict.py")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    print("====== Dog Mood Model Trainer ======\n")
    raise SystemExit(main())
