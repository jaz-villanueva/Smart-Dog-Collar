# Moods: From Sensor to Spoken Phrase

What the collar measures, how each measurement is processed, and which evidence leads to which phrase.

**Status:** this describes what the code does. The "expected reliability" column is a judgement from the feature set, not a measurement; no real dog data has been recorded yet.

## The pipeline

| Stage | Where | What happens |
|-------|-------|--------------|
| 1. Sense | Collar (XIAO nRF52840 Sense) | Motion sampled at 50 Hz; sound sampled at 16 kHz and reduced to a summary 25 times a second; beacon signal strength scanned |
| 2. Send | Bluetooth LE | One 47-byte notification every 40 ms: two motion samples, one sound frame, three beacon strengths, battery |
| 3. Add context | Laptop (`ml/collar.py`) | Hour of day, minutes since `fed`, minutes since `went`, and whether you typed `away` |
| 4. Window | Laptop (`ml/features.py`) | 8-second windows (400 motion rows, 200 sound frames), a new one every 4 seconds, 55 features each |
| 5. Classify | Laptop (`ml/train_mood_model.py`) | Random Forest: 300 trees, at least 2 samples per leaf, classes weighted to balance |
| 6. Decide | Laptop (`ml/live_predict.py`) | Average the last 3 predictions (12 s). Speak only if the top mood reaches 50%. Repeat the same mood only after 60 s. |

## Signals collected

| Signal | Hardware | Raw form | Sent as |
|--------|----------|----------|---------|
| Acceleration, 3 axes | LSM6DS3TR-C (on the XIAO), I2C | g, read at 50 Hz | int16, 0.01 m/s² |
| Rotation rate, 3 axes | LSM6DS3TR-C | deg/s, read at 50 Hz | int16, 0.1 deg/s |
| Loudness | PDM microphone (on the XIAO) | 640 samples (40 ms) at 16 kHz, mean removed | RMS, uint16 |
| Dominant frequency | PDM microphone | Loudest bin of a 512-point Hann-windowed FFT, 94 Hz – 8 kHz | bin number × 31.25 Hz |
| Zero-crossing rate | PDM microphone | Sign changes in 512 samples | count ÷ 2 |
| Sound spectrum | PDM microphone | Mean FFT magnitude in 12 bands, roughly logarithmic from 94 Hz to 8 kHz | 8 × log2(1 + magnitude) per band |
| Location | nRF52840 radio, passive scan a quarter of the time | RSSI of `DogMood-Bowl`, `-Door`, `-Bed` (ESP32 beacons) | int8 dBm; unseen after 10 s |
| Battery | Built-in divider on P0.31 | 12-bit ADC, 2.4 V reference, × 1510/510 | 0.02 V steps |
| Time since meal / potty, owner away, hour | You, typing `fed`, `went`, `away`, `home` | Timestamps kept in `data/context_state.json` | Columns added by the laptop |

Sound band edges in Hz: 94, 156, 219, 312, 437, 625, 875, 1250, 1781, 2531, 3594, 5094, 8000.

## Features computed per 8-second window

| Group | Features | Computed from |
|-------|----------|---------------|
| Movement amount | `accel_mean`, `accel_std`, `accel_max`, `accel_range`, `jerk_mean`, `active_fraction` | Length of the acceleration vector; `active_fraction` is the share of samples more than 1 m/s² away from gravity |
| Movement rhythm | `motion_slow_share` (0.5–3 Hz), `motion_medium_share` (3–8 Hz), `motion_fast_share` (8–25 Hz), `motion_peak_hz` | FFT of the acceleration length |
| Turning | `gyro_mean`, `gyro_std`, `gyro_max` | Length of the rotation-rate vector |
| Loudness | `loudness_mean`, `loudness_std`, `loudness_max` | log10 of RMS per frame |
| Panting | `hiss_level`, `pant_strength`, `pant_rate_hz` | Energy above about 2.5 kHz, and how strongly loudness pulses at 1.5–8 Hz |
| Voice | `vocal_fraction`, `vocal_bursts`, `vocal_pitch_hz`, `vocal_pitch_std`, `vocal_zcr`, `vocal_band_0…11` | Frames well above the window's quiet level; their pitch and the shape of their spectrum |
| Breathing (experimental) | `breath_strength`, `breath_rate_hz` | 0.2–1.5 Hz share of the most active rotation axis |
| Location | `rssi_bowl`, `rssi_door`, `rssi_bed` | Mean signal strength; −110 when unheard |
| Context | `hour`, `mins_since_fed`, `mins_since_potty`, `owner_away` | Last row of the window |
| Optional | `hr_mean`, `hr_std`, `hrv_rmssd`; `cam_*` | Chest strap; cage camera. −1 when absent. |

The direction of gravity is not used, so the model does not know his posture (lying, sitting, standing) from the collar alone.

## Mood → phrase

The phrases are in [`ml/moods.json`](../ml/moods.json); one of the two is picked at random.

| Mood | Phrases | Sensors | Signals that should carry it | Features | Expected reliability |
|------|---------|---------|------------------------------|----------|----------------------|
| Playful | "I want to play!" / "Let's run!" | Motion, microphone | Large, bursty movement and fast turning; short barks | `accel_std`, `jerk_mean`, `gyro_*`, `active_fraction`, `vocal_bursts` | Good |
| Sleepy | "I want to sleep." / "I need a nap." | Motion, microphone, bed beacon | Stillness, silence, slow breathing rock, strong bed signal | `active_fraction`, `accel_std`, `breath_*`, `loudness_mean`, `rssi_bed` | Good; blurs with content and sad |
| Alert | "Someone's here!" / "What was that?" | Microphone, motion, door beacon | Standing still, sharp repeated barks | `vocal_bursts`, `vocal_pitch_hz`, `vocal_band_*`, `loudness_max`, `rssi_door` | Fair to good |
| Hungry | "I'm hungry!" / "Is it dinner time yet?" | Bowl beacon, typed context | Long time since `fed`, strong bowl signal, pacing, whining | `mins_since_fed`, `rssi_bowl`, `hour`, `motion_slow_share` | Mostly a timer you keep by hand |
| Potty | "I need to go outside!" / "I need to pee!" | Door beacon, typed context, motion | Long time since `went`, strong door signal, circling | `mins_since_potty`, `rssi_door`, `gyro_mean`, `motion_slow_share` | Mostly a timer |
| Lonely | "I'm lonely." / "Come back, I miss you." | Typed context, microphone, door beacon | `away` typed; long whines or howls | `owner_away`, `vocal_fraction`, `vocal_pitch_hz`, `rssi_door` | Largely repeats the `away` flag |
| Anxious | "I'm worried." / "Something's wrong." | Motion, microphone | Pacing, trembling at 8–25 Hz, panting | `motion_fast_share`, `motion_slow_share`, `hiss_level`, `pant_strength` | Weak; blurs with stressed |
| Stressed | "This is too much." / "Help!" | Motion, microphone | As anxious, plus loud surroundings and yelps | `hiss_level`, `pant_strength`, `loudness_mean`, `vocal_pitch_hz` | Weak |
| Content | "All is well." / "Pet me?" | Motion, microphone | Little movement, quiet, recently fed | `active_fraction`, `loudness_mean`, `mins_since_fed` | Weak; blurs with sleepy |
| Sad | "I'm sad." / "I feel down." | Motion, microphone | Little, slow movement and silence | `accel_std`, `gyro_mean`, `loudness_mean` | Weakest; looks like resting |

The model is not told which features belong to which mood. It learns that from your labelled recordings, and the trainer prints the ten features it actually relied on.

## Starter dataset and model

[`data/starter/`](../data/starter/) holds a **synthetic** dataset and [`ml/starter_model/`](../ml/starter_model/) a model trained on it. They exist so the scripts can be run before any recording. They say nothing about a real dog; see [`data/starter/README.md`](../data/starter/README.md).
