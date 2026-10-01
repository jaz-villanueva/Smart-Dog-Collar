#!/usr/bin/env python3
"""
Where Is He? Indoor tracking for the Smart Dog Collar
Shows which beacon the dog is nearest (bowl, door or bed), keeps a log of
where he spent his time, and raises an alarm when the collar goes out of range.

This is room-level tracking inside the home, from Bluetooth signal strength.
It is not GPS and cannot find a dog that has left the house. See docs/TRACKING.md.

    python track.py                # show and log where he is
    python track.py --near -65     # he must be closer to a beacon to count as "at" it
    python track.py --mute         # print the alarm without speaking it
"""

import argparse
import asyncio
import csv
import statistics
import time
from collections import deque
from datetime import datetime

from collar import BEACONS, DATA_DIR, CollarStream, require_bleak
from live_predict import speak

LOG_FILE = DATA_DIR / "track_log.csv"
SAMPLE_HZ = 50
SMOOTH_SECONDS = 3     # signal strength jumps about, so take the median over this long
NEAR_DBM = -70         # weaker than this and he is not "at" that beacon
SWITCH_MARGIN_DB = 6   # another beacon must be this much stronger to take over
LOST_SECONDS = 5       # no packets for this long means out of range
RETRY_SECONDS = 5
ELSEWHERE = "elsewhere"


class ZoneTracker:
    """Turns collar rows into a steady answer to "which beacon is he at?"."""

    def __init__(self, near_dbm=NEAR_DBM, margin_db=SWITCH_MARGIN_DB):
        self.near_dbm = near_dbm
        self.margin_db = margin_db
        self.recent = {name: deque(maxlen=SMOOTH_SECONDS * SAMPLE_HZ) for name in BEACONS}
        self.zone = None
        self.since = None
        self.rows = 0

    def strengths(self):
        """Median signal strength of each beacon heard at least half the time."""
        result = {}
        for name, values in self.recent.items():
            heard = [v for v in values if v is not None]
            if len(heard) * 2 >= len(values) > 0:
                result[name] = statistics.median(heard)
        return result

    def update(self, row, now):
        """Add one row. Returns (zone left, when he arrived there, when he left) on a change."""
        for name in BEACONS:
            value = row[f"rssi_{name}"]
            self.recent[name].append(None if value == "" else value)
        self.rows += 1
        if self.rows % SAMPLE_HZ:   # decide once a second
            return None

        strengths = self.strengths()
        best = max(strengths, key=strengths.get, default=None)
        zone = self.zone
        if zone not in strengths or strengths[zone] < self.near_dbm:
            zone = ELSEWHERE
        if best is not None and strengths[best] >= self.near_dbm and best != zone:
            # Stay put unless the new beacon is clearly stronger, or he was nowhere
            if zone == ELSEWHERE or strengths[best] >= strengths[zone] + self.margin_db:
                zone = best

        if zone == self.zone:
            return None
        left = (self.zone, self.since, now) if self.zone is not None else None
        self.zone, self.since = zone, now
        return left

    def finish(self, now):
        """Close the current visit, for example when the collar is lost."""
        left = (self.zone, self.since, now) if self.zone is not None else None
        self.zone = self.since = None
        for values in self.recent.values():
            values.clear()
        return left


class TrackSession:
    def __init__(self, tracker, log_path=LOG_FILE, mute=False):
        self.tracker = tracker
        self.log_path = log_path
        self.mute = mute
        self.stream = CollarStream(self.on_row)
        self.last_packet = 0.0
        self.lost = False

    def log_visit(self, visit):
        if visit is None:
            return
        zone, start, end = visit
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.log_path.exists()
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["arrived", "left", "zone", "seconds"])
            writer.writerow([datetime.fromtimestamp(start).isoformat(timespec="seconds"),
                             datetime.fromtimestamp(end).isoformat(timespec="seconds"),
                             zone, round(end - start)])

    def on_row(self, row, now):
        self.last_packet = now
        if self.lost:
            self.lost = False
            print(f"[{time.strftime('%H:%M:%S')}] Collar is back in range.")
        visit = self.tracker.update(row, now)
        if visit is not None or self.tracker.since == now:
            self.log_visit(visit)
            strengths = ", ".join(f"{k} {v:.0f}" for k, v in self.tracker.strengths().items())
            place = "not near any beacon" if self.tracker.zone == ELSEWHERE else f"at his {self.tracker.zone}"
            print(f"[{time.strftime('%H:%M:%S')}] He is {place}  ({strengths or 'no beacons heard'} dBm)")

    def raise_alarm(self):
        if self.lost:
            return
        self.lost = True
        self.log_visit(self.tracker.finish(time.time()))
        print(f"[{time.strftime('%H:%M:%S')}] OUT OF RANGE: the collar cannot be heard. "
              "It is switched off, flat, or more than about 10 m away.")
        if not self.mute:
            speak("I can't hear the collar.")

    async def watch(self, client):
        """Runs while connected; raises the alarm if the packets stop."""
        self.last_packet = time.time()
        while client.is_connected:
            await asyncio.sleep(1)
            if time.time() - self.last_packet > LOST_SECONDS:
                self.raise_alarm()

    async def run(self):
        print("[TRACK] Ctrl+C to stop. Visits are logged to", self.log_path)
        try:
            while True:
                await self.stream.run(self.watch)
                self.raise_alarm()
                self.stream.last_seq = None
                await asyncio.sleep(RETRY_SECONDS)
        finally:
            self.log_visit(self.tracker.finish(time.time()))


def main():
    parser = argparse.ArgumentParser(description="Show and log which beacon the dog is nearest")
    parser.add_argument("--near", type=float, default=NEAR_DBM, metavar="DBM",
                        help=f"signal strength that counts as being at a beacon (default {NEAR_DBM})")
    parser.add_argument("--mute", action="store_true", help="print the out-of-range alarm without speaking it")
    args = parser.parse_args()

    require_bleak()
    try:
        asyncio.run(TrackSession(ZoneTracker(args.near), mute=args.mute).run())
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Stopped.")


if __name__ == "__main__":
    print("====== Dog Collar Tracker ======\n")
    main()
