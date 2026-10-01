"""
Cage camera for the dog mood model.

A fixed camera looks at his cage. From each frame this finds the dog's outline
and reports where it is, how big it is, and how much it is moving. It does not
track his tail or ears; see README "Known Limitations".

    python camera.py --camera 0 --save-background   # once, with the cage empty
    python camera.py --camera 0                     # preview what the tracker sees

The empty-cage picture lets the tracker see his whole outline even when he is
asleep. Without it, the tracker only sees him while he moves.
"""

import argparse
import csv
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from collar import CAMERA_COLUMNS, DATA_DIR

BACKGROUND_FILE = DATA_DIR / "cage_background.png"
PROCESS_WIDTH = 320       # frames are shrunk to this width before analysis
MIN_DOG_AREA = 0.002      # smaller shapes are treated as noise
DOG_THRESHOLD = 20        # brightness difference from the empty cage that counts as "dog"
MOTION_THRESHOLD = 15     # brightness change between frames that counts as movement
LIGHTING_CHANGE = 0.6     # if this much of the picture differs, the lights changed
TARGET_FPS = 10
BLANK = dict.fromkeys(CAMERA_COLUMNS, "")


def parse_source(text):
    """A camera index such as 0, or a stream URL or video file path."""
    return int(text) if str(text).isdigit() else text


class DogFinder:
    """Finds the dog in each frame of a fixed camera view.

    background is a picture of the empty cage (any size, colour or grey).
    """

    def __init__(self, background=None):
        import cv2
        self.cv2 = cv2
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.empty_cage = None if background is None else self._prepare(background).astype(np.float32)
        self.subtractor = cv2.createBackgroundSubtractorMOG2(history=600, varThreshold=25,
                                                             detectShadows=False)
        self.previous = None
        self.last = dict(BLANK)

    def _prepare(self, frame):
        cv2 = self.cv2
        height = int(frame.shape[0] * PROCESS_WIDTH / frame.shape[1])
        small = cv2.resize(frame, (PROCESS_WIDTH, height))
        if small.ndim == 3:
            small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(small, (5, 5), 0)

    def _dog_mask(self, small):
        cv2 = self.cv2
        if self.empty_cage is None:
            # No empty-cage picture: only what moved recently stands out
            return cv2.morphologyEx(self.subtractor.apply(small), cv2.MORPH_OPEN, self.kernel)

        # A light switched on or off brightens the whole picture at once:
        # shift the empty-cage picture by the same amount before comparing
        current = small.astype(np.float32)
        self.empty_cage += float(np.median(current - self.empty_cage))

        difference = cv2.absdiff(current, self.empty_cage)
        mask = (difference > DOG_THRESHOLD).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)

        if (mask > 0).mean() > LIGHTING_CHANGE:
            # The picture no longer resembles the empty cage (night vision
            # switched on, or the camera moved). Report nothing rather than guess.
            return np.zeros_like(mask)

        # Follow slow lighting drift quickly where the dog is not, and very
        # slowly where he is, so a moved blanket stops counting as "dog" after
        # several minutes. The price: a dog asleep that long fades too, and
        # the tracker then holds his last position.
        dog = cv2.dilate(mask, self.kernel, iterations=4)
        cv2.accumulateWeighted(small, self.empty_cage, 0.01, mask=cv2.bitwise_not(dog))
        cv2.accumulateWeighted(small, self.empty_cage, 0.0002, mask=dog)
        return mask

    def update(self, frame):
        """Analyse one frame and return the camera columns."""
        cv2 = self.cv2
        small = self._prepare(frame)

        motion = 0.0
        if self.previous is not None:
            motion = float((cv2.absdiff(small, self.previous) > MOTION_THRESHOLD).mean())
        self.previous = small

        mask = self._dog_mask(small)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        biggest = max(contours, key=cv2.contourArea, default=None)
        if biggest is not None and cv2.contourArea(biggest) >= MIN_DOG_AREA * mask.size:
            x, y, w, h = cv2.boundingRect(biggest)
            height = mask.shape[0]
            self.last = {
                "cam_x": round((x + w / 2) / PROCESS_WIDTH, 3),
                "cam_y": round((y + h / 2) / height, 3),
                "cam_w": round(w / PROCESS_WIDTH, 3),
                "cam_h": round(h / height, 3),
                "cam_area": round(cv2.contourArea(biggest) / mask.size, 4),
                "cam_motion": round(motion, 4),
            }
        elif self.last["cam_x"] != "":
            # Lost sight of him (no empty-cage picture, or the lights changed).
            # He is still in the cage, so keep his last position.
            self.last = {**self.last, "cam_motion": round(motion, 4)}
        return self.last


class CameraTracker:
    """Reads the camera on a background thread and keeps the latest result.

    With save_dir set, it also saves video.mp4 and frames.csv (frame number and
    time of each frame) so the session can be labelled afterwards.
    """

    def __init__(self, source, save_dir=None, background_file=BACKGROUND_FILE):
        import cv2
        self.cv2 = cv2
        self.capture = cv2.VideoCapture(parse_source(source))
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open camera '{source}'")

        background = cv2.imread(str(background_file)) if Path(background_file).exists() else None
        if background is None:
            print("[CAMERA] No empty-cage picture; he will only be seen while moving.")
            print("[CAMERA] Take one with: python camera.py --camera <source> --save-background")
        self.finder = DogFinder(background)

        self.save_dir = Path(save_dir) if save_dir else None
        self.frame = None
        self._latest = dict(BLANK)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        self.capture.release()

    def latest(self):
        with self._lock:
            return dict(self._latest)

    def _run(self):
        writer, frames_file, frames_csv, count = None, None, None, 0
        try:
            while not self._stop.is_set():
                started = time.time()
                ok, frame = self.capture.read()
                if not ok:
                    time.sleep(0.2)
                    continue

                result = self.finder.update(frame)
                with self._lock:
                    self._latest = result
                    self.frame = frame

                if self.save_dir:
                    if writer is None:
                        self.save_dir.mkdir(parents=True, exist_ok=True)
                        size = (frame.shape[1], frame.shape[0])
                        writer = self.cv2.VideoWriter(str(self.save_dir / "video.mp4"),
                                                      self.cv2.VideoWriter_fourcc(*"mp4v"),
                                                      TARGET_FPS, size)
                        frames_file = open(self.save_dir / "frames.csv", "w", newline="")
                        frames_csv = csv.writer(frames_file)
                        frames_csv.writerow(["frame", "time"])
                    writer.write(frame)
                    # Same clock and format as host_time in the collar CSV
                    stamp = datetime.fromtimestamp(started).isoformat(timespec="milliseconds")
                    frames_csv.writerow([count, stamp])
                    count += 1

                time.sleep(max(0.0, 1.0 / TARGET_FPS - (time.time() - started)))
        finally:
            if writer is not None:
                writer.release()
                frames_file.close()


def save_background(source):
    """Save a picture of the empty cage for the tracker to compare against."""
    import cv2
    capture = cv2.VideoCapture(parse_source(source))
    frame = None
    for _ in range(30):  # let the camera settle its exposure
        ok, grabbed = capture.read()
        if ok:
            frame = grabbed
    capture.release()
    if frame is None:
        print(f"[CAMERA] Could not read from camera '{source}'")
        return 1
    BACKGROUND_FILE.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(BACKGROUND_FILE), frame)
    print(f"[CAMERA] Saved empty-cage picture to {BACKGROUND_FILE}")
    print("[CAMERA] Retake it if you move the camera, the cage or his bedding.")
    return 0


def preview(source):
    """Show the camera with the tracker's box drawn on it. Press q to close."""
    import cv2
    tracker = CameraTracker(source).start()
    print("[CAMERA] Press q in the video window to close.")
    try:
        while True:
            frame, found = tracker.frame, tracker.latest()
            if frame is not None:
                frame = frame.copy()
                if found["cam_x"] != "":
                    h, w = frame.shape[:2]
                    x0 = int((found["cam_x"] - found["cam_w"] / 2) * w)
                    y0 = int((found["cam_y"] - found["cam_h"] / 2) * h)
                    cv2.rectangle(frame, (x0, y0),
                                  (x0 + int(found["cam_w"] * w), y0 + int(found["cam_h"] * h)),
                                  (0, 200, 255), 2)
                    cv2.putText(frame, f"motion {found['cam_motion']:.3f}", (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
                cv2.imshow("Dog camera", frame)
            if cv2.waitKey(50) & 0xFF == ord("q"):
                break
    finally:
        tracker.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preview the cage camera tracker")
    parser.add_argument("--camera", default="0", help="camera index, stream URL or video file")
    parser.add_argument("--save-background", action="store_true",
                        help="save a picture of the EMPTY cage, then exit")
    args = parser.parse_args()
    raise SystemExit(save_background(args.camera) if args.save_background else preview(args.camera))
