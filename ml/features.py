"""
Window features for the dog mood model.

train_mood_model.py and live_predict.py both call compute_window_features, so
training and live use always see the same numbers.
"""

import numpy as np
import pandas as pd

from collar import BAND_COLUMNS, CAMERA_COLUMNS, SAMPLES_PER_PACKET

SAMPLE_HZ = 50        # motion rows per second
FRAME_HZ = SAMPLE_HZ // SAMPLES_PER_PACKET  # sound frames per second
WINDOW_SECONDS = 8
HOP_SECONDS = 4       # windows overlap by half
GRAVITY = 9.81

WINDOW = WINDOW_SECONDS * SAMPLE_HZ
HOP = HOP_SECONDS * SAMPLE_HZ
CONTEXT_COLUMNS = ["hour", "mins_since_fed", "mins_since_potty", "owner_away"]
HISS_BANDS = slice(9, 12)  # above ~2.5 kHz, where panting noise sits
MIN_BEATS_FOR_HRV = 4
MISSING = -1.0
CAMERA_FEATURES = ["cam_x", "cam_y", "cam_aspect", "cam_area",
                   "cam_motion_mean", "cam_motion_std", "cam_travel"]


def band_share(signal, rate_hz, low, high, floor=0.5):
    """Share of a signal's energy between low and high Hz, and its peak frequency there."""
    spectrum = np.abs(np.fft.rfft(signal - signal.mean())) ** 2
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / rate_hz)
    total = spectrum[freqs >= floor].sum()
    band = (freqs >= low) & (freqs < high)
    if total <= 0 or not band.any():
        return 0.0, 0.0
    return spectrum[band].sum() / total, freqs[band][np.argmax(spectrum[band])]


def numeric(window_df, column):
    """A column as floats, with blanks and missing columns as NaN."""
    if column not in window_df:
        return np.full(len(window_df), np.nan)
    return pd.to_numeric(window_df[column], errors="coerce").to_numpy(dtype=float)


def compute_window_features(window_df, use_context=True):
    """Compute features from one 8-second window of collar rows."""
    features = {}

    # Motion: how much, how sudden, and at what rhythm
    accel = np.linalg.norm(window_df[["accel_x", "accel_y", "accel_z"]].to_numpy(dtype=float), axis=1)
    features["accel_mean"] = accel.mean()
    features["accel_std"] = accel.std()
    features["accel_max"] = accel.max()
    features["accel_range"] = accel.max() - accel.min()
    features["jerk_mean"] = np.abs(np.diff(accel)).mean() * SAMPLE_HZ
    features["active_fraction"] = (np.abs(accel - GRAVITY) > 1.0).mean()
    features["motion_slow_share"], _ = band_share(accel, SAMPLE_HZ, 0.5, 3)      # walking, pacing
    features["motion_medium_share"], _ = band_share(accel, SAMPLE_HZ, 3, 8)      # trotting, scratching
    features["motion_fast_share"], _ = band_share(accel, SAMPLE_HZ, 8, SAMPLE_HZ)  # shaking, trembling
    _, features["motion_peak_hz"] = band_share(accel, SAMPLE_HZ, 0.5, SAMPLE_HZ)

    gyro = np.linalg.norm(window_df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(dtype=float), axis=1)
    features["gyro_mean"] = gyro.mean()
    features["gyro_std"] = gyro.std()
    features["gyro_max"] = gyro.max()

    # Sound is measured once per packet, so take one row per packet
    frames = window_df.iloc[::SAMPLES_PER_PACKET]
    rms = frames["audio_rms"].to_numpy(dtype=float)
    loudness = np.log10(rms + 1.0)
    bands = frames[BAND_COLUMNS].to_numpy(dtype=float)
    features["loudness_mean"] = loudness.mean()
    features["loudness_std"] = loudness.std()
    features["loudness_max"] = loudness.max()

    # Panting is a hiss that pulses a few times a second
    features["hiss_level"] = bands[:, HISS_BANDS].mean() - bands.mean()
    features["pant_strength"], features["pant_rate_hz"] = band_share(loudness, FRAME_HZ, 1.5, 8)

    # A frame counts as vocal when it stands well above the window's quiet level
    vocal = rms > 4.0 * np.percentile(rms, 10) + 50.0
    features["vocal_fraction"] = vocal.mean()
    features["vocal_bursts"] = np.count_nonzero(np.diff(vocal.astype(int)) == 1)
    if vocal.any():
        pitch = frames["dom_freq_hz"].to_numpy(dtype=float)[vocal]
        features["vocal_pitch_hz"] = pitch.mean()
        features["vocal_pitch_std"] = pitch.std()
        features["vocal_zcr"] = frames["zcr"].to_numpy(dtype=float)[vocal].mean()
        # Shape of the sound across the 12 bands, with overall loudness removed:
        # this is what separates a bark from a whine, a growl or a howl
        shape = bands[vocal].mean(axis=0)
        shape = shape - shape.mean()
    else:
        features["vocal_pitch_hz"] = 0.0
        features["vocal_pitch_std"] = 0.0
        features["vocal_zcr"] = 0.0
        shape = np.zeros(len(BAND_COLUMNS))
    for column, value in zip(BAND_COLUMNS, shape):
        features[f"vocal_{column}"] = value

    # Heart (chest strap, optional): rate, and beat-to-beat variability
    heart_rate = numeric(window_df, "heart_rate")
    heart_rate = heart_rate[~np.isnan(heart_rate)]
    features["hr_mean"] = heart_rate.mean() if len(heart_rate) else MISSING
    features["hr_std"] = heart_rate.std() if len(heart_rate) else MISSING
    rr = numeric(window_df, "rr_ms")
    rr = rr[~np.isnan(rr)]
    if len(rr) >= MIN_BEATS_FOR_HRV:
        features["hrv_rmssd"] = np.sqrt(np.mean(np.diff(rr) ** 2))
    else:
        features["hrv_rmssd"] = MISSING

    # Breathing while resting: a slow, regular rocking of the sensor.
    # Only meaningful when he is still, so the model also sees active_fraction.
    gyro_axes = window_df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(dtype=float)
    steadiest = gyro_axes[:, np.argmax(gyro_axes.var(axis=0))]
    features["breath_strength"], features["breath_rate_hz"] = band_share(
        steadiest, SAMPLE_HZ, 0.2, 1.5, floor=0.2)

    # Cage camera (optional): where he is, his outline, and how much he moves.
    # A wide, low outline is a dog lying down; a tall one is sitting or standing.
    cam = {c: numeric(window_df, c) for c in CAMERA_COLUMNS}
    seen = ~np.isnan(cam["cam_x"])
    if seen.any():
        x, y = cam["cam_x"][seen], cam["cam_y"][seen]
        features["cam_x"] = x.mean()
        features["cam_y"] = y.mean()
        features["cam_aspect"] = (cam["cam_w"][seen] / np.maximum(cam["cam_h"][seen], 1e-3)).mean()
        features["cam_area"] = cam["cam_area"][seen].mean()
        features["cam_motion_mean"] = cam["cam_motion"][seen].mean()
        features["cam_motion_std"] = cam["cam_motion"][seen].std()
        features["cam_travel"] = np.hypot(np.diff(x), np.diff(y)).sum()
    else:
        for name in CAMERA_FEATURES:
            features[name] = MISSING

    # Context the sensors cannot see
    if use_context:
        for column in CONTEXT_COLUMNS:
            value = numeric(window_df, column)[-1]
            features[column] = MISSING if np.isnan(value) else value

    return features
