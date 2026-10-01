"""
Shared collar code: BLE connection, packet decoding, heart-rate strap and context.

Used by ble_data_logger.py (recording) and live_predict.py (live moods).
"""

import json
import struct
import time
from collections import deque
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path

# UUIDs and name (must match firmware)
DEVICE_NAME = "DogMood-Collar"
SENSOR_CHAR_UUID = "87654321-4321-8765-4321-fedcba987654"

# Standard Bluetooth Heart Rate Measurement, sent by chest straps such as the Polar H10
HR_CHAR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
HR_STALE_SECONDS = 5

# Packet layout (must match SensorPacket in the firmware)
NUM_BANDS = 12
PACKET_FORMAT = f"<H12hHBBB{NUM_BANDS}B"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 43 bytes
BIN_HZ = 16000 / 512
SAMPLES_PER_PACKET = 2
SAMPLE_WRAP = 65536 * SAMPLES_PER_PACKET

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR.parent / "data"
CONTEXT_FILE = DATA_DIR / "context_state.json"

PHRASES = json.loads((ML_DIR / "moods.json").read_text(encoding="utf-8"))
MOODS = list(PHRASES)

# Things only you know, which the sensors cannot see
EVENTS = {
    "fed": "he just ate",
    "went": "he just peed or pooped",
    "away": "you are leaving him alone",
    "home": "you are back with him",
}

BAND_COLUMNS = [f"band_{i}" for i in range(NUM_BANDS)]
SENSOR_COLUMNS = [
    "sample",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "audio_rms", "dom_freq_hz", "zcr", "flags",
    *BAND_COLUMNS,
    "heart_rate", "rr_ms",
    "hour", "mins_since_fed", "mins_since_potty", "owner_away",
]


def decode_packet(data):
    """Turn one notification into two 50 Hz rows of sensor values in real units.

    Both rows carry the same sound frame, because sound is measured once per packet.
    """
    fields = struct.unpack(PACKET_FORMAT, data)
    seq, imu, (rms, dom_bin, zcr, flags), bands = fields[0], fields[1:13], fields[13:17], fields[17:]

    sound = {
        "audio_rms": rms,
        "dom_freq_hz": dom_bin * BIN_HZ,
        "zcr": zcr,
        "flags": flags,
        **dict(zip(BAND_COLUMNS, bands)),
    }
    rows = []
    for i in range(SAMPLES_PER_PACKET):
        ax, ay, az, gx, gy, gz = imu[i * 6:(i + 1) * 6]
        rows.append({
            "sample": seq * SAMPLES_PER_PACKET + i,
            "accel_x": ax / 100.0, "accel_y": ay / 100.0, "accel_z": az / 100.0,  # m/s^2
            "gyro_x": gx / 10.0, "gyro_y": gy / 10.0, "gyro_z": gz / 10.0,        # deg/s
            **sound,
        })
    return rows


def parse_heart_rate(data):
    """Decode a Heart Rate Measurement into (beats per minute, [RR intervals in ms])."""
    flags = data[0]
    if flags & 0x01:
        bpm, offset = struct.unpack_from("<H", data, 1)[0], 3
    else:
        bpm, offset = data[1], 2
    if flags & 0x08:  # energy expended field
        offset += 2
    rr_ms = []
    if flags & 0x10:
        for i in range(offset, len(data) - 1, 2):
            rr_ms.append(struct.unpack_from("<H", data, i)[0] * 1000.0 / 1024.0)
    return bpm, rr_ms


class Context:
    """Feeding, potty and owner-away state, kept between runs."""

    def __init__(self, path=CONTEXT_FILE):
        self.path = Path(path)
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.state = {"last_fed": None, "last_potty": None, "owner_away": False}

    def log_event(self, event):
        now = time.time()
        if event == "fed":
            self.state["last_fed"] = now
        elif event == "went":
            self.state["last_potty"] = now
        else:
            self.state["owner_away"] = event == "away"
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        print(f"[EVENT] Noted: {EVENTS[event]}")

    def values(self, now):
        """Context columns for a row; blank when the event was never logged."""
        def minutes_since(stamp):
            return "" if stamp is None else round((now - stamp) / 60.0, 1)

        return {
            "hour": datetime.fromtimestamp(now).hour,
            "mins_since_fed": minutes_since(self.state["last_fed"]),
            "mins_since_potty": minutes_since(self.state["last_potty"]),
            "owner_away": int(self.state["owner_away"]),
        }


class CollarStream:
    """Receives collar packets (and optional heart rate) and hands complete rows to on_row."""

    def __init__(self, on_row, context=None):
        self.on_row = on_row
        self.context = context or Context()
        self.last_seq = None
        self.dropped = 0
        self.heart_rate = None
        self.heart_rate_time = 0.0
        self.rr_queue = deque()

    def handle_collar(self, sender, data):
        """Handle one incoming sensor packet"""
        if len(data) != PACKET_SIZE:
            print(f"[ERROR] Expected {PACKET_SIZE} bytes, got {len(data)}. "
                  "Old firmware, or the BLE MTU was not raised.")
            return

        rows = decode_packet(bytes(data))
        seq = rows[0]["sample"] // SAMPLES_PER_PACKET
        if self.last_seq is not None:
            self.dropped += (seq - self.last_seq - 1) % 65536
        self.last_seq = seq

        now = time.time()
        context = self.context.values(now)
        fresh = now - self.heart_rate_time < HR_STALE_SECONDS
        for row in rows:
            row["heart_rate"] = self.heart_rate if fresh else ""
            row["rr_ms"] = round(self.rr_queue.popleft(), 1) if self.rr_queue else ""
            row.update(context)
            self.on_row(row, now)

    def handle_heart_rate(self, sender, data):
        self.heart_rate, rr_ms = parse_heart_rate(bytes(data))
        self.heart_rate_time = time.time()
        self.rr_queue.extend(rr_ms)

    async def run(self, body, hr_name=None):
        """Connect, stream rows to on_row, and run body(client) until it returns."""
        from bleak import BleakClient, BleakScanner

        print(f"[SCAN] Looking for '{DEVICE_NAME}'...")
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)
        if device is None:
            print("[SCAN] Collar not found. Make sure it's powered on and advertising.")
            return False

        hr_device = None
        if hr_name:
            print(f"[SCAN] Looking for heart-rate strap '{hr_name}'...")
            hr_device = await BleakScanner.find_device_by_filter(
                lambda d, adv: hr_name.lower() in (d.name or adv.local_name or "").lower(),
                timeout=15.0,
            )
            if hr_device is None:
                print("[SCAN] Strap not found. Wet the electrodes and make sure he is wearing it.")
                return False

        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(BleakClient(
                device,
                disconnected_callback=lambda _: print("\n[BLE] Collar disconnected. Press Enter."),
            ))
            print(f"[CONNECT] Collar connected ({device.address})")
            await client.start_notify(SENSOR_CHAR_UUID, self.handle_collar)

            if hr_device is not None:
                hr_client = await stack.enter_async_context(BleakClient(hr_device))
                print(f"[CONNECT] Heart-rate strap connected ({hr_device.name})")
                await hr_client.start_notify(HR_CHAR_UUID, self.handle_heart_rate)

            await body(client)
        return True


def require_bleak():
    try:
        import bleak  # noqa: F401
    except ImportError:
        print("[ERROR] Missing 'bleak' library. Install with:")
        print("       pip install bleak")
        raise SystemExit(1)
