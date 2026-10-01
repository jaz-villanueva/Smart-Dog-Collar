#!/usr/bin/env python3
"""
Label a recording from its video.

Plays the video of an unattended recording. While it plays, press a number
key to say what mood he is in; every frame shown from then on gets that mood
until you press another key. Rewind and replay to correct a stretch. Until
you press a key, playing the video changes nothing, so it is safe to review.

    python label_video.py                 # newest recording
    python label_video.py data/recordings/20261001-140000

Keys:
    1-9, 0   set the mood (the list is shown on screen)
    u        erase labels from here on
    k        stop labelling (keep what is there)
    space    pause / resume
    a / d    back / forward 5 seconds
    - / +    slower / faster
    q        save and quit

Saves labels.csv (your progress) and labelled.csv (training rows) in the
recording's folder. train_mood_model.py picks up labelled.csv automatically.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from collar import DATA_DIR, MOODS

RECORDINGS_DIR = DATA_DIR / "recordings"
UNLABELLED = -1
KEEP = -2  # play without changing any labels
SKIP_SECONDS = 5
SPEEDS = [0.5, 1, 2, 4, 8]


def load_frame_moods(recording, frame_count):
    """Mood index for every frame, restored from labels.csv if it exists."""
    moods = np.full(frame_count, UNLABELLED)
    labels_file = recording / "labels.csv"
    if labels_file.exists():
        saved = pd.read_csv(labels_file)
        saved = saved[saved["frame"] < frame_count]
        moods[saved["frame"]] = saved["mood"].map(MOODS.index)
    return moods


def save_frame_moods(recording, frame_moods):
    frames = np.flatnonzero(frame_moods != UNLABELLED)
    pd.DataFrame({"frame": frames, "mood": [MOODS[i] for i in frame_moods[frames]]}).to_csv(
        recording / "labels.csv", index=False)


def write_labelled_rows(recording, frame_moods):
    """Give each collar row the mood of the video frame showing at that moment.

    Returns the number of labelled rows written to labelled.csv.
    """
    collar = pd.read_csv(recording / "collar.csv", dtype={"session_id": str, "mood": str})
    # Both files hold local clock times from the same computer; compare them in seconds
    def seconds(column):
        return pd.to_datetime(column).astype("datetime64[ns]").astype("int64").to_numpy() / 1e9

    frame_times = seconds(pd.read_csv(recording / "frames.csv")["time"])[:len(frame_moods)]
    row_times = seconds(collar["host_time"])

    # The frame on screen at each row's time is the last one that started before it
    frame = np.searchsorted(frame_times, row_times, side="right") - 1
    in_video = (frame >= 0) & (row_times <= frame_times[-1] + 1.0)
    mood = np.where(in_video, frame_moods[np.clip(frame, 0, len(frame_moods) - 1)], UNLABELLED)

    # Every unbroken stretch of one mood becomes its own session
    stretch = np.cumsum(np.r_[True, mood[1:] != mood[:-1]])
    collar["mood"] = [MOODS[i] if i != UNLABELLED else "" for i in mood]
    collar["session_id"] = [f"{recording.name}-v{s}" for s in stretch]

    labelled = collar[mood != UNLABELLED]
    labelled.to_csv(recording / "labelled.csv", index=False)
    return len(labelled)


def draw_overlay(cv2, frame, position, total, fps, frame_mood, brush, speed, paused):
    lines = [
        f"{position / fps:6.1f} s / {total / fps:.1f} s   x{speed}{'   PAUSED' if paused else ''}",
        f"This frame: {MOODS[frame_mood] if frame_mood != UNLABELLED else '(no label)'}"
        f"   Now marking: {'nothing' if brush == KEEP else 'erase' if brush == UNLABELLED else MOODS[brush]}",
        "  ".join(f"{(i + 1) % 10}={m}" for i, m in enumerate(MOODS[:5])),
        "  ".join(f"{(i + 1) % 10}={m}" for i, m in enumerate(MOODS[5:], start=5)),
    ]
    for i, text in enumerate(lines):
        origin = (10, 24 + i * 22)
        cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
        cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)


def label(recording):
    import cv2

    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 10
    if total == 0:
        print(f"[ERROR] No video frames in {recording}")
        return 1

    frame_moods = load_frame_moods(recording, total)
    mood, speed, paused, position = KEEP, 1, False, 0
    frame = None

    while True:
        if not paused or frame is None:
            ok, frame = capture.read()
            if not ok:
                paused = True  # end of video: wait for a key
                capture.set(cv2.CAP_PROP_POS_FRAMES, total - 1)
                continue
            position = int(capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            if mood != KEEP:
                frame_moods[position] = mood

        shown = frame.copy()
        draw_overlay(cv2, shown, position, total, fps, frame_moods[position], mood, SPEEDS[speed], paused)
        cv2.imshow("Label video", shown)

        key = cv2.waitKey(max(1, int(1000 / fps / SPEEDS[speed]))) & 0xFF
        if key == ord("q"):
            break
        elif ord("0") <= key <= ord("9"):
            choice = (key - ord("0") - 1) % 10
            if choice < len(MOODS):
                mood = choice
                frame_moods[position] = mood
        elif key == ord("u"):
            mood = UNLABELLED
            frame_moods[position] = mood
        elif key == ord("k"):
            mood = KEEP
        elif key == ord(" "):
            paused = not paused
        elif key in (ord("a"), ord("d")):
            step = int(SKIP_SECONDS * fps) * (1 if key == ord("d") else -1)
            capture.set(cv2.CAP_PROP_POS_FRAMES, min(max(position + step, 0), total - 1))
            frame = None
        elif key in (ord("-"), ord("+"), ord("=")):
            speed = min(max(speed + (-1 if key == ord("-") else 1), 0), len(SPEEDS) - 1)

    capture.release()
    cv2.destroyAllWindows()

    save_frame_moods(recording, frame_moods)
    rows = write_labelled_rows(recording, frame_moods)
    print(f"[LABEL] Saved {rows} labelled rows ({rows / 50 / 60:.1f} minutes) to "
          f"{recording / 'labelled.csv'}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Label an unattended recording from its video")
    parser.add_argument("recording", nargs="?", help="recording folder (default: the newest)")
    args = parser.parse_args()

    if args.recording:
        recording = Path(args.recording)
    else:
        recordings = sorted(p for p in RECORDINGS_DIR.glob("*") if (p / "video.mp4").exists())
        if not recordings:
            print(f"[ERROR] No recordings in {RECORDINGS_DIR}")
            print("[ERROR] Make one: python ble_data_logger.py --camera 0 --unattended")
            return 1
        recording = recordings[-1]

    print(f"[LABEL] {recording}")
    return label(recording)


if __name__ == "__main__":
    print("====== Dog Mood Video Labeller ======\n")
    sys.exit(main())
