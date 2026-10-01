#!/usr/bin/env python3
"""
BLE Data Logger for Smart Dog Collar
Records collar sensor packets to CSV while you label the dog's mood from the keyboard.

Each stretch of one mood is a "session". The trainer keeps whole sessions together
when it tests the model, so record every mood on several separate occasions.
"""

import asyncio
import csv
import json
import struct
import time
from datetime import datetime
from pathlib import Path

# UUIDs and name (must match firmware)
DEVICE_NAME = "DogMood-Collar"
SENSOR_CHAR_UUID = "87654321-4321-8765-4321-fedcba987654"

# Packet layout (must match SensorPacket in the firmware)
PACKET_FORMAT = "<H6hHBBBB"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 20 bytes
BIN_HZ = 16000 / 512

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR.parent / "data"
CSV_FILE = DATA_DIR / "sensor_readings.csv"
CONTEXT_FILE = DATA_DIR / "context_state.json"

MOODS = list(json.loads((ML_DIR / "moods.json").read_text(encoding="utf-8")))

# Things only you know, which the motion and sound sensors cannot see
EVENTS = {
    "fed": "he just ate",
    "went": "he just peed or pooped",
    "away": "you are leaving him alone",
    "home": "you are back with him",
}

FIELDNAMES = [
    "host_time", "seq", "session_id", "mood",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "audio_rms", "dom_freq_hz", "centroid_hz", "zcr", "flags",
    "hour", "mins_since_fed", "mins_since_potty", "owner_away",
]


def decode_packet(data):
    """Turn one 20-byte notification into sensor values in real units."""
    seq, ax, ay, az, gx, gy, gz, rms, dom_bin, centroid_bin, zcr, flags = struct.unpack(
        PACKET_FORMAT, data
    )
    return {
        "seq": seq,
        "accel_x": ax / 100.0, "accel_y": ay / 100.0, "accel_z": az / 100.0,  # m/s^2
        "gyro_x": gx / 10.0, "gyro_y": gy / 10.0, "gyro_z": gz / 10.0,        # deg/s
        "audio_rms": rms,
        "dom_freq_hz": dom_bin * BIN_HZ,
        "centroid_hz": centroid_bin * BIN_HZ,
        "zcr": zcr,
        "flags": flags,
    }


def resolve_command(text, choices):
    """Match a typed prefix to exactly one of the choices, or return None."""
    matches = [c for c in choices if c.startswith(text)]
    return matches[0] if len(matches) == 1 else None


class DogCollarLogger:
    def __init__(self):
        self.current_mood = None
        self.session_id = None
        self.session_count = 0
        self.last_seq = None
        self.dropped = 0
        self.unlabeled = 0
        self.counts = {}
        self.csv_file = None
        self.csv_writer = None
        self.context = self._load_context()

    def _load_context(self):
        if CONTEXT_FILE.exists():
            return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
        return {"last_fed": None, "last_potty": None, "owner_away": False}

    def _save_context(self):
        CONTEXT_FILE.write_text(json.dumps(self.context, indent=2), encoding="utf-8")

    def context_values(self, now):
        """Context columns for a row; blank when the event was never logged."""
        def minutes_since(stamp):
            return "" if stamp is None else round((now - stamp) / 60.0, 1)

        return {
            "hour": datetime.fromtimestamp(now).hour,
            "mins_since_fed": minutes_since(self.context["last_fed"]),
            "mins_since_potty": minutes_since(self.context["last_potty"]),
            "owner_away": int(self.context["owner_away"]),
        }

    def open_csv(self):
        DATA_DIR.mkdir(exist_ok=True)
        is_new = not CSV_FILE.exists()
        self.csv_file = open(CSV_FILE, "a", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=FIELDNAMES)
        if is_new:
            self.csv_writer.writeheader()

    def notification_handler(self, sender, data):
        """Handle one incoming sensor packet"""
        if len(data) != PACKET_SIZE:
            print(f"[ERROR] Expected {PACKET_SIZE} bytes, got {len(data)}. Reflash the firmware?")
            return

        row = decode_packet(bytes(data))

        if self.last_seq is not None:
            self.dropped += (row["seq"] - self.last_seq - 1) % 65536
        self.last_seq = row["seq"]

        if self.current_mood is None:
            self.unlabeled += 1
            return

        now = time.time()
        row["host_time"] = datetime.fromtimestamp(now).isoformat(timespec="milliseconds")
        row["session_id"] = self.session_id
        row["mood"] = self.current_mood
        row.update(self.context_values(now))
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

    def log_event(self, event):
        now = time.time()
        if event == "fed":
            self.context["last_fed"] = now
        elif event == "went":
            self.context["last_potty"] = now
        else:
            self.context["owner_away"] = event == "away"
        self._save_context()
        print(f"[EVENT] Noted: {EVENTS[event]}")

    def print_status(self):
        print(f"[STATUS] mood={self.current_mood or 'paused'}  dropped packets={self.dropped}")
        for mood in MOODS:
            if mood in self.counts:
                print(f"         {mood:10s} {self.counts[mood] / 25:7.0f} s recorded this run")

    def print_help(self):
        print("\n[LOG] Type a mood (a unique prefix is enough) and press Enter:")
        print("      " + ", ".join(MOODS))
        print("      Events: " + ", ".join(f"'{k}' = {v}" for k, v in EVENTS.items()))
        print("      'u' = pause labeling, '?' = status, 'q' = quit\n")

    async def command_loop(self, client):
        self.print_help()
        while client.is_connected:
            text = (await asyncio.to_thread(input, "> ")).strip().lower()
            if text == "q":
                break
            elif text == "u":
                self.set_mood(None)
            elif text == "?":
                self.print_status()
            elif text in EVENTS:
                self.log_event(text)
            elif text and resolve_command(text, MOODS):
                self.set_mood(resolve_command(text, MOODS))
            elif text:
                print(f"[MOOD] '{text}' is unknown or ambiguous.")
                self.print_help()

    async def run(self):
        from bleak import BleakClient, BleakScanner

        print(f"[SCAN] Looking for '{DEVICE_NAME}'...")
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)
        if device is None:
            print("[SCAN] Collar not found. Make sure it's powered on and advertising.")
            return

        print(f"[CONNECT] Connecting to {device.address}...")
        async with BleakClient(
            device, disconnected_callback=lambda _: print("\n[BLE] Collar disconnected. Press Enter.")
        ) as client:
            print("[CONNECT] Connected")
            self.open_csv()
            try:
                await client.start_notify(SENSOR_CHAR_UUID, self.notification_handler)
                await self.command_loop(client)
                if client.is_connected:
                    await client.stop_notify(SENSOR_CHAR_UUID)
            finally:
                self.csv_file.close()

        self.print_status()
        print(f"[LOG] Data saved to {CSV_FILE}")


if __name__ == "__main__":
    print("====== Dog Collar BLE Data Logger ======\n")

    try:
        import bleak  # noqa: F401
    except ImportError:
        print("[ERROR] Missing 'bleak' library. Install with:")
        print("       pip install bleak")
        raise SystemExit(1)

    try:
        asyncio.run(DogCollarLogger().run())
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Logger stopped.")
