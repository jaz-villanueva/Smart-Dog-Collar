// TinyTalk core: packet decoding, window features, the mood model and the zone tracker.
// No DOM here, so check_parity.mjs can run it under Node against the Python scripts.
//
// decodePacket mirrors ml/collar.py, windowFeatures mirrors ml/features.py and
// ZoneTracker mirrors ml/track.py. Change them together.

export const DEVICE_NAME = 'DogMood-Collar';
export const SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0';
export const SENSOR_CHAR_UUID = '87654321-4321-8765-4321-fedcba987654';

export const PACKET_SIZE = 47;
export const NUM_BANDS = 12;
export const BEACONS = ['bowl', 'door', 'bed'];
const BEACON_UNSEEN = -128;
const BIN_HZ = 16000 / 512;

export const SAMPLE_HZ = 50;
export const FRAME_HZ = 25;              // one packet = one sound frame = two motion samples
export const WINDOW_PACKETS = 8 * FRAME_HZ;
export const HOP_PACKETS = 4 * FRAME_HZ;
const GRAVITY = 9.81;
const MISSING = -1;
const BEACON_ABSENT = -110;

// ---------------------------------------------------------------- Packet

/** Turn one 47-byte notification (a DataView) into sensor values in real units. */
export function decodePacket(view) {
  const motion = [];
  for (let i = 0; i < 2; i++) {
    const at = 2 + i * 12;
    const sample = [];
    for (let j = 0; j < 3; j++) sample.push(view.getInt16(at + j * 2, true) / 100);      // m/s^2
    for (let j = 3; j < 6; j++) sample.push(view.getInt16(at + j * 2, true) / 10);       // deg/s
    motion.push(sample);
  }
  const bands = [];
  for (let i = 0; i < NUM_BANDS; i++) bands.push(view.getUint8(31 + i));
  const rssi = BEACONS.map((_, i) => {
    const value = view.getInt8(43 + i);
    return value === BEACON_UNSEEN ? null : value;
  });
  const battery = view.getUint8(46);
  return {
    seq: view.getUint16(0, true),
    motion,
    rms: view.getUint16(26, true),
    domHz: view.getUint8(28) * BIN_HZ,
    zcr: view.getUint8(29),
    flags: view.getUint8(30),
    bands,
    rssi,
    battery: battery ? battery * 0.02 : null,
  };
}

// ---------------------------------------------------------------- Maths

const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
const std = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((v) => (v - m) ** 2))); };
const max = (a) => a.reduce((m, v) => (v > m ? v : m), -Infinity);
const min = (a) => a.reduce((m, v) => (v < m ? v : m), Infinity);

function percentile(values, percent) {
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * percent / 100;
  const low = Math.floor(position);
  const high = Math.min(low + 1, sorted.length - 1);
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}

/** Power at each frequency from 0 to half the sample rate, with the mean removed. */
function powerSpectrum(signal) {
  const n = signal.length;
  const m = mean(signal);
  const power = [];
  for (let k = 0; k <= Math.floor(n / 2); k++) {
    let re = 0, im = 0;
    for (let t = 0; t < n; t++) {
      const angle = 2 * Math.PI * k * t / n;
      re += (signal[t] - m) * Math.cos(angle);
      im -= (signal[t] - m) * Math.sin(angle);
    }
    power.push(re * re + im * im);
  }
  return power;
}

/** Share of a signal's energy between low and high Hz, and its peak frequency there. */
function bandShare(power, n, rateHz, low, high, floor = 0.5) {
  let total = 0, inBand = 0, peak = -1, peakHz = 0, any = false;
  for (let k = 0; k < power.length; k++) {
    const hz = k * rateHz / n;
    if (hz >= floor) total += power[k];
    if (hz >= low && hz < high) {
      any = true;
      inBand += power[k];
      if (power[k] > peak) { peak = power[k]; peakHz = hz; }
    }
  }
  return total <= 0 || !any ? [0, 0] : [inBand / total, peakHz];
}

// ---------------------------------------------------------------- Features

/**
 * Features of one 8-second window.
 * packets: WINDOW_PACKETS decoded packets, oldest first.
 * context: { hour, minsSinceFed, minsSincePotty, ownerAway }; null where unknown.
 */
export function windowFeatures(packets, context) {
  const f = {};
  const samples = packets.flatMap((p) => p.motion);
  const n = samples.length;

  const accel = samples.map((s) => Math.hypot(s[0], s[1], s[2]));
  f.accel_mean = mean(accel);
  f.accel_std = std(accel);
  f.accel_max = max(accel);
  f.accel_range = max(accel) - min(accel);
  f.jerk_mean = mean(accel.slice(1).map((v, i) => Math.abs(v - accel[i]))) * SAMPLE_HZ;
  f.active_fraction = mean(accel.map((v) => (Math.abs(v - GRAVITY) > 1 ? 1 : 0)));
  const accelPower = powerSpectrum(accel);
  [f.motion_slow_share] = bandShare(accelPower, n, SAMPLE_HZ, 0.5, 3);
  [f.motion_medium_share] = bandShare(accelPower, n, SAMPLE_HZ, 3, 8);
  [f.motion_fast_share] = bandShare(accelPower, n, SAMPLE_HZ, 8, SAMPLE_HZ);
  [, f.motion_peak_hz] = bandShare(accelPower, n, SAMPLE_HZ, 0.5, SAMPLE_HZ);

  const gyro = samples.map((s) => Math.hypot(s[3], s[4], s[5]));
  f.gyro_mean = mean(gyro);
  f.gyro_std = std(gyro);
  f.gyro_max = max(gyro);

  const rms = packets.map((p) => p.rms);
  const loudness = rms.map((v) => Math.log10(v + 1));
  f.loudness_mean = mean(loudness);
  f.loudness_std = std(loudness);
  f.loudness_max = max(loudness);

  // Panting is a hiss that pulses a few times a second
  f.hiss_level = mean(packets.flatMap((p) => p.bands.slice(9, 12))) - mean(packets.flatMap((p) => p.bands));
  [f.pant_strength, f.pant_rate_hz] = bandShare(powerSpectrum(loudness), loudness.length, FRAME_HZ, 1.5, 8);

  // A frame counts as vocal when it stands well above the window's quiet level
  const quiet = 4 * percentile(rms, 10) + 50;
  const vocal = rms.map((v) => v > quiet);
  const voiced = packets.filter((_, i) => vocal[i]);
  f.vocal_fraction = voiced.length / packets.length;
  f.vocal_bursts = vocal.filter((v, i) => i > 0 && v && !vocal[i - 1]).length;
  let shape = new Array(NUM_BANDS).fill(0);
  if (voiced.length) {
    const pitch = voiced.map((p) => p.domHz);
    f.vocal_pitch_hz = mean(pitch);
    f.vocal_pitch_std = std(pitch);
    f.vocal_zcr = mean(voiced.map((p) => p.zcr));
    shape = shape.map((_, band) => mean(voiced.map((p) => p.bands[band])));
    const level = mean(shape);
    shape = shape.map((v) => v - level);
  } else {
    f.vocal_pitch_hz = f.vocal_pitch_std = f.vocal_zcr = 0;
  }
  shape.forEach((value, band) => { f[`vocal_band_${band}`] = value; });

  // No heart-rate strap or cage camera in the app
  f.hr_mean = f.hr_std = f.hrv_rmssd = MISSING;
  for (const name of ['cam_x', 'cam_y', 'cam_aspect', 'cam_area', 'cam_motion_mean',
    'cam_motion_std', 'cam_travel']) f[name] = MISSING;

  // Breathing while resting: slow rocking on the rotation axis that moves most
  const axes = [3, 4, 5].map((axis) => samples.map((s) => s[axis]));
  const variances = axes.map((a) => std(a) ** 2);
  const busiest = axes[variances.indexOf(max(variances))];
  [f.breath_strength, f.breath_rate_hz] = bandShare(powerSpectrum(busiest), n, SAMPLE_HZ, 0.2, 1.5, 0.2);

  BEACONS.forEach((name, i) => {
    const heard = packets.map((p) => p.rssi[i]).filter((v) => v !== null);
    f[`rssi_${name}`] = heard.length ? mean(heard) : BEACON_ABSENT;
  });

  const known = (value) => (value === null || value === undefined ? MISSING : value);
  f.hour = known(context.hour);
  f.mins_since_fed = known(context.minsSinceFed);
  f.mins_since_potty = known(context.minsSincePotty);
  f.owner_away = context.ownerAway ? 1 : 0;
  return f;
}

// ---------------------------------------------------------------- Model

/** Class probabilities from the exported Random Forest (see ml/export_app_model.py). */
export function predictProba(model, features) {
  // scikit-learn compares 32-bit floats against the thresholds
  const x = model.feature_names.map((name) => Math.fround(features[name]));
  const total = new Array(model.classes.length).fill(0);
  for (const tree of model.trees) {
    let node = 0;
    while (tree.left[node] !== -1) {
      node = x[tree.feature[node]] <= tree.threshold[node] ? tree.left[node] : tree.right[node];
    }
    tree.value[node].forEach((p, c) => { total[c] += p; });
  }
  return total.map((v) => v / model.trees.length);
}

/** Feeds packets in, hands a smoothed mood out every 4 seconds. Mirrors ml/live_predict.py. */
export class MoodPredictor {
  constructor(model, smoothWindows = 3) {
    this.model = model;
    this.smoothWindows = smoothWindows;
    this.reset();
  }

  reset() {
    this.packets = [];
    this.recent = [];
    this.sincePrediction = 0;
    this.lastSeq = null;
  }

  /** Returns { mood, confidence, sure } when a new prediction is ready, else null. */
  add(packet, context) {
    // After dropped packets the window would mix two moments, so start over
    if (this.lastSeq !== null && ((packet.seq - this.lastSeq) & 0xffff) !== 1) this.reset();
    this.lastSeq = packet.seq;

    this.packets.push(packet);
    if (this.packets.length > WINDOW_PACKETS) this.packets.shift();
    this.sincePrediction++;
    if (this.packets.length < WINDOW_PACKETS || this.sincePrediction < HOP_PACKETS) return null;
    this.sincePrediction = 0;

    this.recent.push(predictProba(this.model, windowFeatures(this.packets, context)));
    if (this.recent.length > this.smoothWindows) this.recent.shift();
    const proba = this.model.classes.map((_, c) => mean(this.recent.map((p) => p[c])));
    const best = proba.indexOf(max(proba));
    return {
      mood: this.model.classes[best],
      confidence: proba[best],
      sure: proba[best] >= this.model.confidence_threshold,
    };
  }
}

// ---------------------------------------------------------------- Where is he

export const ELSEWHERE = 'elsewhere';

/** Which beacon is he at? Mirrors ml/track.py. */
export class ZoneTracker {
  constructor(nearDbm = -70, marginDb = 6, smoothSeconds = 3) {
    this.nearDbm = nearDbm;
    this.marginDb = marginDb;
    this.keep = smoothSeconds * FRAME_HZ;
    this.reset();
  }

  reset() {
    this.recent = BEACONS.map(() => []);
    this.zone = null;
    this.count = 0;
  }

  /** Median strength of each beacon heard at least half the time; null otherwise. */
  strengths() {
    return this.recent.map((values) => {
      const heard = values.filter((v) => v !== null).sort((a, b) => a - b);
      if (!values.length || heard.length * 2 < values.length) return null;
      const mid = heard.length >> 1;
      return heard.length % 2 ? heard[mid] : (heard[mid - 1] + heard[mid]) / 2;
    });
  }

  /** Add one packet. Returns the new zone when it changes, else null. */
  add(packet) {
    packet.rssi.forEach((value, i) => {
      this.recent[i].push(value);
      if (this.recent[i].length > this.keep) this.recent[i].shift();
    });
    if (++this.count % FRAME_HZ) return null;   // decide once a second

    const strengths = this.strengths();
    const at = (name) => strengths[BEACONS.indexOf(name)];
    let best = null;
    BEACONS.forEach((name) => {
      if (at(name) !== null && (best === null || at(name) > at(best))) best = name;
    });
    let zone = this.zone;
    if (zone === null || zone === ELSEWHERE || at(zone) === null || at(zone) < this.nearDbm) zone = ELSEWHERE;
    if (best !== null && at(best) >= this.nearDbm && best !== zone) {
      // Stay put unless the new beacon is clearly stronger, or he was nowhere
      if (zone === ELSEWHERE || at(best) >= at(zone) + this.marginDb) zone = best;
    }
    if (zone === this.zone) return null;
    this.zone = zone;
    return zone;
  }
}
