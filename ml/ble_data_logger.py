#!/usr/bin/env python3
"""
BLE Data Logger for Smart Dog Collar
Records collar sensor packets to CSV while you label the dog's mood from the keyboard.

Each stretch of one mood is a "session". The trainer keeps whole sessions together
when it tests the model, so record every mood on several separate occasions.

    python ble_data_logger.py               # collar only
    python ble_data_logger.py --hr Polar    # collar + heart-rate chest strap
"""

import argparse
import asyncio
import csv
from datetime import datetime

from collar import (DATA_DIR, EVENTS, MOODS, SENSOR_COLUMNS, CollarStream,
                    require_bleak)

CSV_FILE = DATA_DIR / "sensor_readings.csv"
FIELDNAMES = ["host_time", "session_id", "mood", *SENSOR_COLUMNS]
SAMPLE_HZ = 50


def resolve_command(text, choices):
    """Match a typed prefix to exactly one of the choices, or return None."""
    matches = [c for c in choices if c.startswith(text)]
    return matches[0] if len(matches) == 1 else None


class DogCollarLogger:
    def __init__(self, csv_path=CSV_FILE, context=None):
        self.csv_path = csv_path
        self.stream = CollarStream(self.write_row, context)
        self.current_mood = None
        self.session_id = None
        self.session_count = 0
        self.counts = {}
        self.csv_file = None
        self.csv_writer = None

    def open_csv(self):
        self.csv_path.parent.mkdir(exist_ok=True)
        is_new = not self.csv_path.exists()
        self.csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=FIELDNAMES)
        if is_new:
            self.csv_writer.writeheader()

    def write_row(self, row, now):
        if self.current_mood is None:
            return
        row["host_time"] = datetime.fromtimestamp(now).isoformat(timespec="milliseconds")
        row["session_id"] = self.session_id
        row["mood"] = self.current_mood
        self.csv_writer.writerow(row)
        self.counts[self.current_mood] = self.counts.get(self.current_mood, 0) + 1

    def set_mood(self, mood):
        """Start a new labelled session, or pause labelling with mood=None"""
        self.current_mood = mood
        if mood is None:
            print("[MOOD] Paused. Packets are ignored until you pick a mood.")
            return
        self.session_count += 1
        self.session_id = f"{datetime.now():%Y%m%d-%H%M%S}-{self.session_count}"
        print(f"[MOOD] Now labeling as '{mood}' (session {self.session_id})")

    def print_status(self):
        heart = self.stream.heart_rate
        print(f"[STATUS] mood={self.current_mood or 'paused'}  "
              f"dropped packets={self.stream.dropped}  "
              f"heart rate={heart if heart is not None else 'no strap'}  "
              f"battery={self.stream.battery_v or '?'} V")
        for mood in MOODS:
            if mood in self.counts:
                print(f"         {mood:10s} {self.counts[mood] / SAMPLE_HZ:7.0f} s recorded this run")

    def print_help(self):
        print("\n[LOG] Type a mood (a unique prefix is enough) and press Enter:")
        print("      " + ", ".join(MOODS))
        print("      Events: " + ", ".join(f"'{k}' = {v}" for k, v in EVENTS.items()))
        print("      'u' = pause labeling, '?' = status, 'q' = quit\n")

    async def command_loop(self, client):
        self.open_csv()
        self.print_help()
        try:
            while client.is_connected:
                text = (await asyncio.to_thread(input, "> ")).strip().lower()
                if text == "q":
                    break
                elif text == "u":
                    self.set_mood(None)
                elif text == "?":
                    self.print_status()
                elif text in EVENTS:
                    self.stream.context.log_event(text)
                elif text and resolve_command(text, MOODS):
                    self.set_mood(resolve_command(text, MOODS))
                elif text:
                    print(f"[MOOD] '{text}' is unknown or ambiguous.")
                    self.print_help()
        finally:
            self.current_mood = None
            self.csv_file.close()

    async def run(self, hr_name=None):
        if await self.stream.run(self.command_loop, hr_name):
            self.print_status()
            print(f"[LOG] Data saved to {self.csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record labelled dog collar data")
    parser.add_argument("--hr", metavar="NAME",
                        help="also record a BLE heart-rate strap whose name contains NAME, e.g. Polar")
    args = parser.parse_args()

    print("====== Dog Collar BLE Data Logger ======\n")
    require_bleak()

    try:
        asyncio.run(DogCollarLogger().run(args.hr))
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Logger stopped.")
