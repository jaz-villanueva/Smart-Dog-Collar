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

ML_DIR = Path(__file__).resolve().parent
DATA_FILE = ML_DIR.parent / "data" / "sensor_readings.csv"
OUTPUT_DIR = ML_DIR / "trained_models"

MOODS = list(json.loads((ML_DIR / "moods.json").read_text(encoding="utf-8")))

SAMPLE_HZ = 25        # packet rate of the firmware
WINDOW_SECONDS = 8
HOP_SECONDS = 4       # windows overlap by half
MAX_GAP_PACKETS = 5   # a longer run of dropped packets splits the recording
MIN_SESSIONS = 2      # per mood, to be able to test on an unseen session
GRAVITY = 9.81

WINDOW = WINDOW_SECONDS * SAMPLE_HZ
HOP = HOP_SECONDS * SAMPLE_HZ
CONTEXT_COLUMNS = ["hour", "mins_since_fed", "mins_since_potty", "owner_away"]


def band_fractions(signal):
    """Share of motion energy in slow, medium and fast bands, plus the peak frequency."""
    spectrum = np.abs(np.fft.rfft(signal - signal.mean())) ** 2
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / SAMPLE_HZ)
    total = spectrum[freqs >= 0.5].sum()
    if total <= 0:
        return 0.0, 0.0, 0.0, 0.0

    def share(low, high):
        return spectrum[(freqs >= low) & (freqs < high)].sum() / total

    peak = freqs[np.argmax(np.where(freqs >= 0.5, spectrum, 0))]
    return share(0.5, 3), share(3, 8), share(8, SAMPLE_HZ / 2 + 1), peak


def compute_window_features(window_df, use_context=True):
    """Compute features from one 8-second window of collar data.

    The mobile app must compute exactly these features, in this order.
    """
    features = {}

    # Motion: how much, how sudden, and at what rhythm
    accel = np.linalg.norm(window_df[["accel_x", "accel_y", "accel_z"]].to_numpy(), axis=1)
    features["accel_mean"] = accel.mean()
    features["accel_std"] = accel.std()
    features["accel_max"] = accel.max()
    features["accel_range"] = accel.max() - accel.min()
    features["jerk_mean"] = np.abs(np.diff(accel)).mean() * SAMPLE_HZ
    features["active_fraction"] = (np.abs(accel - GRAVITY) > 1.0).mean()
    slow, medium, fast, peak = band_fractions(accel)
    features["motion_slow_share"] = slow      # walking, pacing
    features["motion_medium_share"] = medium  # trotting, scratching
    features["motion_fast_share"] = fast      # shaking, trembling
    features["motion_peak_hz"] = peak

    gyro = np.linalg.norm(window_df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(), axis=1)
    features["gyro_mean"] = gyro.mean()
    features["gyro_std"] = gyro.std()
    features["gyro_max"] = gyro.max()

    # Sound: how loud, how often, and at what pitch
    rms = window_df["audio_rms"].to_numpy(dtype=float)
    loudness = np.log10(rms + 1.0)
    features["loudness_mean"] = loudness.mean()
    features["loudness_std"] = loudness.std()
    features["loudness_max"] = loudness.max()

    # A frame counts as vocal when it stands well above the window's quiet level
    vocal = rms > 4.0 * np.percentile(rms, 10) + 50.0
    features["vocal_fraction"] = vocal.mean()
    features["vocal_bursts"] = np.count_nonzero(np.diff(vocal.astype(int)) == 1)
    if vocal.any():
        features["vocal_pitch_hz"] = window_df["dom_freq_hz"].to_numpy()[vocal].mean()
        features["vocal_centroid_hz"] = window_df["centroid_hz"].to_numpy()[vocal].mean()
        features["vocal_zcr"] = window_df["zcr"].to_numpy()[vocal].mean()
    else:
        features["vocal_pitch_hz"] = 0.0
        features["vocal_centroid_hz"] = 0.0
        features["vocal_zcr"] = 0.0

    # Context the sensors cannot see; -1 means the event was never logged
    if use_context:
        for column in CONTEXT_COLUMNS:
            value = window_df[column].iloc[-1] if column in window_df else np.nan
            features[column] = -1.0 if pd.isna(value) else float(value)

    return features


class MoodModelTrainer:
    def __init__(self, data_file, output_dir, use_context=True):
        self.data_file = Path(data_file)
        self.output_dir = Path(output_dir)
        self.use_context = use_context
        self.df = None
        self.model = None
        self.feature_names = None

    def load_data(self):
        """Load sensor data from CSV"""
        print("[DATA] Loading sensor readings...")

        if not self.data_file.exists():
            print(f"[ERROR] Data file not found: {self.data_file}")
            print("[ERROR] Run data logger first: python ble_data_logger.py")
            return False

        self.df = pd.read_csv(self.data_file, dtype={"session_id": str})
        self.df = self.df[self.df["mood"].isin(MOODS)]
        print(f"[DATA] Loaded {len(self.df)} labelled samples "
              f"({len(self.df) / SAMPLE_HZ / 60:.1f} minutes)")

        summary = self.df.groupby("mood").agg(
            sessions=("session_id", "nunique"),
            minutes=("seq", lambda s: round(len(s) / SAMPLE_HZ / 60, 1)),
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
            gap = session_df["seq"].diff().fillna(1).mod(65536)
            for _, run in session_df.groupby((gap > MAX_GAP_PACKETS).cumsum()):
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
            n_estimators=200,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced",  # Handle class imbalance
        )

    def evaluate(self, X, y, groups):
        """Score the model on sessions held out of training"""
        print("\n[EVAL] Testing on held-out sessions...")

        n_splits = min(5, pd.Series(groups).groupby(y).nunique().min())
        folds = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
        y_pred = cross_val_predict(self.new_model(), X, y, groups=groups, cv=folds)

        classes = sorted(set(y))
        accuracy = accuracy_score(y, y_pred)
        baseline = pd.Series(y).value_counts(normalize=True).max()
        print(f"[EVAL] Accuracy:  {accuracy:.1%}  "
              f"(always guessing the most common mood scores {baseline:.1%})")
        print(f"[EVAL] Macro F1:  {f1_score(y, y_pred, average='macro'):.2f}")
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
        return accuracy

    def train_final_model(self, X, y):
        """Fit on every window for the model the app will use"""
        print("\n[TRAIN] Training final model on all sessions...")
        self.model = self.new_model().fit(X, y)

        ranked = sorted(zip(self.model.feature_importances_, self.feature_names), reverse=True)
        print("[TRAIN] Most useful features:")
        for importance, name in ranked[:10]:
            print(f"         {name:22s} {importance:.3f}")

    def save_model(self, accuracy):
        """Save trained model and the details the app needs to use it"""
        model_file = self.output_dir / "dog_mood_model.joblib"
        joblib.dump(self.model, model_file)

        metadata = {
            "classes": list(self.model.classes_),
            "feature_names": self.feature_names,
            "sample_hz": SAMPLE_HZ,
            "window_seconds": WINDOW_SECONDS,
            "held_out_accuracy": round(float(accuracy), 4),
        }
        metadata_file = self.output_dir / "model_metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"\n[SAVE] Model saved to {model_file}")
        print(f"[SAVE] Metadata saved to {metadata_file}")


def main():
    parser = argparse.ArgumentParser(description="Train the dog mood classifier")
    parser.add_argument("--data", default=DATA_FILE, help="labelled CSV from the data logger")
    parser.add_argument("--out", default=OUTPUT_DIR, help="folder for the model and plots")
    parser.add_argument("--no-context", action="store_true",
                        help="ignore time of day, feeding, potty and owner-away columns")
    args = parser.parse_args()

    trainer = MoodModelTrainer(args.data, args.out, use_context=not args.no_context)

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
    accuracy = trainer.evaluate(X, y, groups)
    trainer.train_final_model(X, y)
    trainer.save_model(accuracy)

    print("\n" + "=" * 50)
    print("Model training complete!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    print("====== Dog Mood Model Trainer ======\n")
    raise SystemExit(main())
