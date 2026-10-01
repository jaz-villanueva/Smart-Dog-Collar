# 🐕 DIY Smart Dog Collar: Real-Time Mood Detection + AI Translation

A one-month vlog project building a wearable dog mood detector using an ESP32, a motion sensor, a microphone, and machine learning. The collar guesses your dog's mood and "says" it as a simple English phrase.

**Status:** In Development (1-Month Vlog Sprint)  
**Timeline:** October 2026  
**Deliverable:** YouTube vlog + working prototype + open-source code

---

## 🎯 Project Overview

- **Hardware:** ESP32 + MPU6050 (motion) + INMP441 (microphone)
- **Firmware:** Arduino C++, 20-byte binary BLE packets at 25 Hz
- **ML:** Random Forest classifier on 8-second windows of motion, sound and context
- **App:** Flutter mobile app that runs the model and speaks the phrase *(not started)*
- **Ground truth:** the mood you type into the data logger while watching your dog

**Mood Classes:** Playful, Sleepy, Hungry, Potty, Sad, Lonely, Anxious, Alert, Content, Stressed

The list and the phrases for each mood live in [`ml/moods.json`](ml/moods.json). Edit that one file to add, remove or reword them.

### What is built and what is not

| Part | State |
|------|-------|
| Firmware | Written. Not yet compiled or run on hardware. |
| Data logger | Written. Packet decoding and CSV output tested with synthetic packets; not yet run against a real collar. |
| Trainer | Written. Runs end to end on synthetic data; no real dog data yet. |
| Mobile app, collar housing, sample dataset | Not started. |

---

## 📁 Repository Structure

```
dog-mood-collar-vlog/
├── firmware/
│   └── dog_collar_firmware/
│       └── dog_collar_firmware.ino   # ESP32 sketch
├── ml/
│   ├── moods.json                    # Mood classes + spoken phrases
│   ├── ble_data_logger.py            # Record sensor data + label moods
│   ├── train_mood_model.py           # Train and test the classifier
│   └── requirements.txt
├── hardware/
│   ├── BOM.csv                       # Bill of materials
│   └── WIRING_REFERENCE.txt          # Connections, power, bench checks
├── data/                             # Your recordings (git-ignored)
├── app/                              # Flutter app (to be added)
└── docs/                             # Checklists written for the first design*
```

*\*The files in `docs/` still describe the original four-sensor design and need updating.*

---

## 🚀 Quick Start

### 1. Hardware
1. Wire the breadboard from `hardware/WIRING_REFERENCE.txt`. **Read the power section first:** the battery goes on the TP4056 `B+`/`B-` pads, never `IN+`/`IN-`.
2. In Arduino IDE, install ESP32 board support and the **Adafruit MPU6050** library.
3. Flash `firmware/dog_collar_firmware/dog_collar_firmware.ino`.
4. Open the Serial Monitor at 115200 baud and run the bench checks in the wiring reference.

### 2. Data collection
```bash
pip install -r ml/requirements.txt
```
```bash
python ml/ble_data_logger.py
```
Type a mood (a unique prefix is enough, e.g. `hu` for hungry) to start labelling, `u` to pause. Also tell the logger what the sensors cannot see:

| Command | Meaning |
|---------|---------|
| `fed` | he just ate |
| `went` | he just peed or pooped |
| `away` / `home` | you are leaving him alone / you are back |

### 3. Training
```bash
python ml/train_mood_model.py
```
The model and its confusion matrix go to `ml/trained_models/`.

---

## 🏷️ Labelling moods well

Your labels are the ground truth, so the model can only be as good as they are.

- **Label when you are sure.** Pause (`u`) whenever you are not.
- **Anchor each mood to a situation you can recognise:**

| Mood | Good moments to record |
|------|------------------------|
| Playful | Play bows, bringing a toy, zoomies |
| Sleepy | Yawning, curling up, settling in his bed |
| Hungry | Before a late meal: hovering at the bowl, following you to the kitchen |
| Potty | Hours since his last break: waiting at the door, circling, sniffing |
| Sad | Low, slow, withdrawn; ignoring toys and people |
| Lonely | Alone after you leave: whining, howling, waiting by the door |
| Anxious | Pacing, panting, trembling (thunder, fireworks, the vet) |
| Alert | Frozen and focused, barking at a sound or visitor |
| Content | Relaxed while being petted or resting near you |
| Stressed | Overwhelmed: too many people, loud noise, being handled |

- **Record every mood on several separate occasions**, at least 5 and ideally 10+, each a minute or more. The trainer tests on occasions it never trained on and skips any mood with fewer than 2.
- **Lonely needs you to be gone.** Start the label, type `away`, and leave the laptop in BLE range (or watch him on a camera).

---

## 📋 Hardware BOM

| Component | Model | Price* | Notes |
|-----------|-------|--------|-------|
| Microcontroller | ESP32-WROOM-32 | — | Already owned |
| IMU | MPU6050 | ₱250 | 6-axis accel + gyro, I2C |
| Microphone | INMP441 | ₱150 | I2S, barks and whines |
| LiPo Battery | 1000mAh 3.7V | ₱300 | With protection circuit |
| Charging | TP4056 with protection | ₱100 | 6-pad module |
| Regulator | HT7333 / MCP1700-3302 | ₱50 | Battery → 3.3V |
| USB-C Port | Breakout | ₱100 | Charging |

**Total new purchases (PH):** about ₱1,850 including perfboard, filament and straps.

*\*Budget estimates. See `hardware/BOM.csv` for the full list.*

The first design also had a MAX30102 heart-rate sensor and an MLX90614 IR thermometer. Both were dropped: the MAX30102 is designed for bare human skin held still, and the MLX90614 would read the fur surface, not body temperature.

---

## 📊 Targets

| Metric | Target | Achieved |
|--------|--------|----------|
| Accuracy on held-out sessions | Clearly above the "most common mood" baseline the trainer prints | — |
| BLE Range | >10m | — |
| Battery Life | 6–8 hrs | — |
| Mood Latency | <10 sec (one 8-second window) | — |
| Vlog Duration | 15–20 min | — |

---

## ⚠️ Known Limitations

- **The model learns your reading of your dog.** There is no instrument that measures a dog's mood, so "accuracy" means agreement with your labels.
- **Hungry and potty lean on context.** They are predicted mostly from the time since you typed `fed` or `went`, so they only work while you keep logging those events. Run the trainer with `--no-context` to see how far motion and sound alone get.
- **Similar moods will be confused.** Expect sad/sleepy/content and anxious/stressed/alert to blur; the confusion matrix shows which.
- **One dog.** A model trained on your dog will not transfer to another.
- The housing is 3D-printed and not waterproof. Do not leave the collar on an unsupervised dog, and never charge it while he is wearing it.

---

## 🎥 Vlog Narrative

**Hook (0:00–0:15):** "I built an AI collar that translates my dog's mood to English"

**Build (0:15–8:00):** Assembly, soldering montage, code walkthrough, data collection time-lapse

**Training (8:00–12:00):** Model training, feature importance, confusion matrix

**Demo (12:00–18:00):** Real-time predictions on actual dog behavior

**Closeout (18:00–20:00):** Learnings, challenges, future improvements

---

## 🤝 Contributing

This is a vlog/learning project, but if you:
- Build this and find improvements
- Adapt it for other animals
- Improve the ML model
- Add new features

Feel free to fork and share your results!

---

## 📝 License

MIT License — See LICENSE file for details

Free to use, modify, and share for personal/educational projects.

---

## 📚 References

- [MPU6050 Datasheet](https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Datasheet1.pdf)
- [INMP441 Datasheet](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf)
- [Random Forest Classifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
- [StratifiedGroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)
- [Bleak (Python BLE)](https://bleak.readthedocs.io/)

---

## 👤 Author

Built by **Jaz Villanueva** (DLSU Computer Engineering)

---

**Last Updated:** October 2026 | **Status:** 🚀 In Progress
