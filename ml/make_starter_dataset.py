#!/usr/bin/env python3
"""
Make the SYNTHETIC starter dataset.

No dog was involved. Each mood is simulated from a hand-written guess at what
the collar would report (how much he moves, what he sounds like, which beacon
he is near, how long since he ate). It exists so the trainer and the live
script can be run end to end before any real recording, and to show the CSV
layout that ble_data_logger.py writes.

    python make_starter_dataset.py

writes data/starter/synthetic_starter.csv.gz. A model trained on it says
nothing about a real dog; replace it with your own recordings.
"""

import numpy as np
import pandas as pd

from collar import BAND_COLUMNS, CAMERA_COLUMNS, DATA_DIR, MOODS, SENSOR_COLUMNS

OUT_FILE = DATA_DIR / "starter" / "synthetic_starter.csv.gz"
SESSIONS_PER_MOOD = 6
SESSION_SECONDS = 40
SAMPLE_HZ, FRAME_HZ = 50, 25
# Upper edge of each sound band in Hz (BAND_EDGES in the firmware x 31.25)
BAND_TOP_HZ = np.array([156, 219, 312, 437, 625, 875, 1250, 1781, 2531, 3594, 5094, 8000])

# move      body movement, m/s^2        stride    its rhythm, Hz
# tremble   fast shaking, m/s^2         turn      rotation, deg/s
# vocal     share of time vocalising    burst     length of one sound, s
# pitch     of the sound, Hz            pant      strength of panting hiss, 0-1
# near      beacon he is beside         fed/potty minutes since, (low, high)
PROFILES = {
    "playful":  dict(move=6.0, stride=4.0, tremble=0.0, turn=150, vocal=0.15, burst=0.2,
                     pitch=700, pant=0.3, near=None, fed=(60, 200), potty=(20, 120), away=0),
    "sleepy":   dict(move=0.05, stride=0.5, tremble=0.0, turn=1, vocal=0.0, burst=0.2,
                     pitch=0, pant=0.0, near="bed", fed=(30, 240), potty=(20, 180), away=0),
    "hungry":   dict(move=1.0, stride=1.5, tremble=0.0, turn=30, vocal=0.10, burst=0.6,
                     pitch=1200, pant=0.0, near="bowl", fed=(300, 480), potty=(20, 180), away=0),
    "potty":    dict(move=1.5, stride=1.8, tremble=0.0, turn=80, vocal=0.06, burst=0.5,
                     pitch=1300, pant=0.0, near="door", fed=(60, 240), potty=(240, 400), away=0),
    "sad":      dict(move=0.15, stride=0.6, tremble=0.0, turn=3, vocal=0.0, burst=0.2,
                     pitch=0, pant=0.0, near=None, fed=(60, 300), potty=(20, 200), away=0),
    "lonely":   dict(move=0.6, stride=1.2, tremble=0.0, turn=15, vocal=0.35, burst=1.5,
                     pitch=600, pant=0.0, near="door", fed=(60, 300), potty=(20, 200), away=1),
    "anxious":  dict(move=2.0, stride=2.0, tremble=0.5, turn=60, vocal=0.05, burst=0.4,
                     pitch=1400, pant=0.8, near=None, fed=(60, 300), potty=(20, 200), away=0),
    "alert":    dict(move=0.2, stride=0.8, tremble=0.0, turn=10, vocal=0.25, burst=0.15,
                     pitch=800, pant=0.0, near="door", fed=(60, 300), potty=(20, 200), away=0),
    "content":  dict(move=0.3, stride=0.8, tremble=0.0, turn=5, vocal=0.0, burst=0.2,
                     pitch=0, pant=0.1, near="bed", fed=(20, 120), potty=(20, 120), away=0),
    "stressed": dict(move=3.0, stride=2.5, tremble=1.0, turn=90, vocal=0.12, burst=0.25,
                     pitch=2000, pant=1.0, near=None, fed=(60, 300), potty=(20, 200), away=0),
}
assert set(PROFILES) == set(MOODS), "one profile per mood in moods.json"


def make_session(mood, index, rng):
    p = PROFILES[mood]
    vary = lambda value: value * rng.uniform(0.7, 1.4)   # no two sessions alike
    n = SESSION_SECONDS * SAMPLE_HZ
    frames = n // 2
    t = np.arange(n) / SAMPLE_HZ

    # Motion: gravity along a random direction, plus stride, trembling and noise
    gravity = rng.normal(size=3)
    gravity *= 9.81 / np.linalg.norm(gravity)
    stride = np.sin(2 * np.pi * vary(p["stride"]) * t + rng.uniform(0, 6.28))
    tremble = np.sin(2 * np.pi * rng.uniform(10, 14) * t)
    accel = (gravity
             + vary(p["move"]) * stride[:, None] * rng.uniform(0.3, 1.0, size=3)
             + vary(p["tremble"]) * tremble[:, None] * rng.uniform(0.3, 1.0, size=3)
             + rng.normal(scale=0.03 + 0.2 * p["move"], size=(n, 3)))
    breathing = 2.0 * np.sin(2 * np.pi * rng.uniform(0.3, 0.6) * t)   # deg/s, seen when still
    gyro = (vary(p["turn"]) * stride[:, None] * rng.uniform(0.2, 1.0, size=3)
            + breathing[:, None] * np.array([1.0, 0.2, 0.1])
            + rng.normal(scale=0.5 + 0.1 * p["turn"], size=(n, 3)))

    # Sound, one frame per packet: quiet room, panting hiss, and bursts of voice
    tf = np.arange(frames) / FRAME_HZ
    vocal = np.zeros(frames, dtype=bool)
    burst_frames = max(1, int(p["burst"] * FRAME_HZ))
    for start in np.flatnonzero(rng.random(frames) < vary(p["vocal"]) / burst_frames):
        vocal[start:start + burst_frames] = True
    pant = vary(p["pant"]) * (0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(2.5, 4.5) * tf))
    rms = rng.uniform(30, 60) + 20 * rng.random(frames) + 400 * pant
    pitch = np.where(vocal, vary(p["pitch"]) * rng.uniform(0.9, 1.1, size=frames),
                     rng.uniform(100, 300, size=frames))
    rms = np.where(vocal, rms + rng.uniform(2000, 8000, size=frames), rms)
    bands = 18 + 4 * rng.random((frames, len(BAND_COLUMNS)))
    bands[:, 9:] += 25 * pant[:, None]
    voice_band = np.searchsorted(BAND_TOP_HZ, pitch)
    for offset, gain in ((0, 45), (1, 25), (-1, 20)):
        column = np.clip(voice_band + offset, 0, len(BAND_COLUMNS) - 1)
        bands[np.flatnonzero(vocal), column[vocal]] += gain

    # Where he is: strong signal from the beacon he is beside, weak from the others
    rssi = {}
    for name in ("bowl", "door", "bed"):
        centre = rng.uniform(-58, -48) if name == p["near"] else rng.uniform(-88, -72)
        rssi[name] = np.round(centre + rng.normal(scale=4, size=frames))

    session = pd.DataFrame({
        "host_time": pd.Timestamp("2026-01-01") + pd.to_timedelta(index * 3600 + t, unit="s"),
        "session_id": f"synthetic-{mood}-{index}",
        "mood": mood,
        "sample": np.arange(n),
        **{f"accel_{axis}": np.round(accel[:, i], 2) for i, axis in enumerate("xyz")},
        **{f"gyro_{axis}": np.round(gyro[:, i], 1) for i, axis in enumerate("xyz")},
        "audio_rms": np.repeat(np.round(rms), 2).astype(int),
        "dom_freq_hz": np.repeat(np.round(pitch / 31.25) * 31.25, 2),
        "zcr": np.repeat(np.clip(np.round(pitch * 0.032), 0, 255), 2).astype(int),
        "flags": 3,
        **{c: np.repeat(np.clip(np.round(bands[:, i]), 0, 255), 2).astype(int)
           for i, c in enumerate(BAND_COLUMNS)},
        **{f"rssi_{name}": np.repeat(values, 2).astype(int) for name, values in rssi.items()},
        "battery_v": 3.9,
        **dict.fromkeys(CAMERA_COLUMNS, ""),
        "heart_rate": "", "rr_ms": "",
        "hour": int(rng.integers(7, 22)),
        "mins_since_fed": round(rng.uniform(*p["fed"]), 1),
        "mins_since_potty": round(rng.uniform(*p["potty"]), 1),
        "owner_away": p["away"],
    })
    return session[["host_time", "session_id", "mood", *SENSOR_COLUMNS]]


def main():
    rng = np.random.default_rng(42)
    sessions = [make_session(mood, i, rng) for mood in MOODS for i in range(SESSIONS_PER_MOOD)]
    data = pd.concat(sessions, ignore_index=True)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT_FILE, index=False)
    print(f"[STARTER] Wrote {len(data)} synthetic rows "
          f"({len(sessions)} sessions of {SESSION_SECONDS} s) to {OUT_FILE}")


if __name__ == "__main__":
    main()
