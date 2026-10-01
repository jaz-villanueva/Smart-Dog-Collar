# 🐕 Smart Dog Collar Build Checklist (1 Month)

## **WEEK 1: Hardware Assembly & Testing**

### Days 1-2: Sensor Procurement
- [ ] Order all sensors (see links below)
- [ ] Check tracking; aim for delivery by end of Week 1
- [ ] Gather Arduino IDE + ESP32 board support (you likely have this)

### Days 3-5: Firmware Development & Testing
- [ ] Download `dog_collar_firmware.ino`
- [ ] Open in Arduino IDE
- [ ] Install libraries:
  ```bash
  # Sketch > Include Library > Manage Libraries
  # Search and install:
  - "Adafruit MPU6050"
  - "Adafruit MLX90614"
  - "ArduinoJSON"
  - (BLEServer is built-in to ESP32)
  ```
- [ ] Connect ESP32 to computer via USB
- [ ] Compile and upload firmware to first ESP32
- [ ] Open Serial Monitor (115200 baud) → should see initialization messages
- [ ] Sensors start arriving → test each on breadboard:
  - [ ] MPU6050: accel/gyro reading on serial
  - [ ] MLX90614: temperature reading
  - [ ] MAX30102: heart rate (need SparkFun library)
  - [ ] INMP441: microphone FFT (requires I2S driver setup)

### Days 6-7: BLE Testing & Serial Logging
- [ ] Connect all sensors to ESP32 on breadboard
- [ ] Upload complete firmware
- [ ] Verify BLE advertising (Serial Monitor should show "BLE initialized")
- [ ] Test with phone (get a free BLE scanner app):
  - [ ] See "DogMood-Collar" in scan results
  - [ ] Connect to it
  - [ ] See sensor data notifications arriving
  - [ ] **RECORD VIDEO** of BLE data streaming (great for vlog intro)

### End of Week 1 Deliverable:
✓ ESP32 + sensors talking on breadboard  
✓ BLE streaming live sensor data  
✓ Serial logs showing valid readings  

---

## **WEEK 2: Data Collection & Collar Assembly**

### Days 1-3: Collar Housing & Integration
- [ ] Design 3D collar housing (lightweight, ~30g max)
  - [ ] Sensors mounted inside
  - [ ] Battery access on one side
  - [ ] USB-C charging port
  - [ ] Velcro strap for adjustment
- [ ] 3D print housing (PETG preferred for durability)
- [ ] Solder sensors to perfboard carrier board
- [ ] Assemble into housing
- [ ] **TEST FIT** on your dog (don't power on yet — safety check)

### Days 4-7: Daily Data Collection
- [ ] Power on collar, connect to phone via BLE
- [ ] Dog wears collar for 8+ hours daily
- [ ] Manually label behavior simultaneously:
  - [ ] **Playful**: chasing, tail wagging, play bow, zoomies
  - [ ] **Anxious**: pacing, whining, ears back, hiding
  - [ ] **Tired**: lying down, slow movements, yawning
  - [ ] **Alert**: ears up, staring, sudden attention
  - [ ] **Content**: calm sitting, light panting, relaxed body
  - [ ] **Stressed**: excessive panting, trembling, aggression indicators
- [ ] **COLLECT VIDEO CLIPS** of each behavior (for vlog overlay)
- [ ] Each day: export sensor CSV from logger
- [ ] Keep backup CSV copies

### End of Week 2 Deliverable:
✓ Assembled collar prototype wearable by dog  
✓ 1000+ labeled sensor readings (minimum)  
✓ Video footage of dog behaviors  
✓ Local CSV backup of all data  

---

## **WEEK 3: ML Model & Mobile App**

### Days 1-2: Model Training
- [ ] Collect all CSV files into `dog_sensor_data/` folder
- [ ] Download `train_mood_model.py`
- [ ] Install Python dependencies:
  ```bash
  pip install pandas scikit-learn matplotlib seaborn joblib
  ```
- [ ] Run training:
  ```bash
  python train_mood_model.py
  ```
- [ ] Check output:
  - [ ] Test accuracy >75% (aim for 80-85%)
  - [ ] Confusion matrix visualization
  - [ ] Feature importance chart (for vlog explanation)
- [ ] If accuracy <75%:
  - [ ] Collect more data (dogs under-represented)
  - [ ] Rerun training
  - [ ] Iterate

### Days 3-5: Mobile App Development
- [ ] Choose platform (Flutter recommended for speed):
  - [ ] Install Flutter SDK (https://flutter.dev/docs/get-started/install)
  - [ ] Create new project: `flutter create dog_mood_app`
- [ ] Add BLE dependency:
  ```yaml
  # pubspec.yaml
  dependencies:
    flutter:
      sdk: flutter
    flutter_blue: ^0.8.0
  ```
- [ ] Build minimal app:
  - [ ] BLE scan + connect to "DogMood-Collar"
  - [ ] Receive sensor data
  - [ ] Load trained model (joblib .pkl → TFLite conversion needed)
  - [ ] Display live mood prediction + confidence
  - [ ] Show mood phrase from dictionary
- [ ] **MOCK VERSION**: Hardcode predictions for demo if model deployment is slow

### Days 6-7: Integration Testing
- [ ] Collar + phone app working together
- [ ] Real-time mood display on app screen
- [ ] **RECORD DEMO VIDEO**:
  - [ ] Dog plays → app shows "Playful" + phrase
  - [ ] Dog naps → app shows "Tired"
  - [ ] Unexpected sound → "Alert"
  - [ ] Get dog's reaction to each prediction (for vlog comedy)

### End of Week 3 Deliverable:
✓ Trained ML model (accuracy >75%)  
✓ Mobile app with live mood prediction  
✓ Full system demo video (at least 3-5 mins)  

---

## **WEEK 4: Vlog Production & Polish**

### Days 1-3: Filming Additional Sequences
- [ ] Re-shoot assembly montage (high quality, well-lit)
- [ ] Get closeups of:
  - [ ] Soldering sensors
  - [ ] Uploading firmware
  - [ ] Dog putting on collar for first time
  - [ ] Serial monitor output
  - [ ] Model training graphs
- [ ] Interview yourself (10-15 sec):
  - [ ] "Why I built this"
  - [ ] "What surprised me"
  - [ ] "What's next?"

### Days 4-6: Video Editing
- [ ] Use DaVinci Resolve (free) or Adobe Premiere
- [ ] Structure:
  - **Hook (0:00–0:20):** "My dog can talk in English"
  - **Build (0:20–8:00):** Assembly + BLE test montage
  - **Data (8:00–11:00):** Time-lapse of data collection, show training graphs
  - **Demo (11:00–17:00):** Real-time mood predictions
  - **Closeout (17:00–end):** Learnings + GitHub link
- [ ] Add captions (especially for technical bits)
- [ ] Add music (royalty-free from YouTube Audio Library)
- [ ] Export in 1080p 60fps

### Day 7: Final Polish & Upload
- [ ] Optimize title & description with keywords:
  - "Arduino ESP32 smart collar"
  - "Dog mood detection AI"
  - "Machine learning wearable"
- [ ] Create custom thumbnail
- [ ] Write detailed description with timestamps & GitHub link
- [ ] Post to YouTube (unlisted first for review, then public)
- [ ] Share on:
  - [ ] Twitter/X (maker community)
  - [ ] Reddit r/arduino, r/esp32, r/MachineLearning
  - [ ] Your DLSU student channels
  - [ ] LinkedIn (if applicable)

### End of Week 4 Deliverable:
✓ Published vlog video (18-20 mins)  
✓ GitHub repo with all code + data documentation  
✓ BOM + build instructions for replication  

---

## **SENSOR ORDERING LINKS**

Copy-paste into your browser:

| Part | Link | Est. Cost | ETA |
|------|------|-----------|-----|
| **ESP32-WROOM-32** (2x) | https://www.amazon.com/HiLetgo-Internet-Development-Microcontroller-Integrated/dp/B0791D7997 | $16 | 2-3d |
| **MAX30102 Heart Rate** | https://www.amazon.com/Sparkfun-MAX30102-Pulse-Oximetry-Module/dp/B07GTBDVRY | $12 | 2-3d |
| **MLX90614 IR Temp** | https://www.amazon.com/UCTRONICS-Contactless-Temperature-Raspberry-Arduino/dp/B07KYJNKLM | $15 | 2-3d |
| **MPU6050 IMU** | https://www.amazon.com/GY-521-MPU-6050-Accelerometer-Gyroscope-Microcontroller/dp/B008BOPN40 | $5 | 2-3d |
| **INMP441 Microphone** | https://www.amazon.com/INMP441-Omnidirectional-Microphone-I2S-Interface-Arduino/dp/B0928YQJ3P | $3 | 3-5d |
| **1000mAh LiPo + TP4056** | https://www.amazon.com/EEMB-Lithium-Rechargeable-Connector-Protection/dp/B08D9SB7QT | $8 | 3-5d |
| **USB-C Breakout** | https://www.amazon.com/Gikfun-Micro-Breakout-Development-Arduino/dp/B01UXHMYCO | $2 | 2-3d |
| **Perfboard + Wires** | (You have already) | $5 | — |
| **3D Filament (PETG 250g)** | https://www.amazon.com/PETG-Filament-1-75MM-Dimensional-Accuracy/dp/B07PGZNM34 | $15 | 2-3d |

**Total: ~$80-100**

---

## **Critical Success Factors**

### Do's ✓
- Start data collection on **Day 1 of Week 2** (don't wait)
- Backup sensor data daily (USB stick, GitHub)
- Label behavior **while wearing collar**, not from memory
- Test each sensor individually before soldering
- Charge battery fully before each data session
- Keep a daily log of issues + solutions (great for vlog blooper reel)

### Don'ts ✗
- Don't over-engineer the collar housing (simple > perfect)
- Don't wait until Week 3 to start collecting data
- Don't rely solely on synthetic/simulated data
- Don't skip testing on actual dog early (comfort/safety check)
- Don't assume BLE will work without testing first

---

## **Vlog Video Tips**

1. **B-roll is everything**: Slow-motion of dog playing, close-ups of components
2. **Keep technical explanations simple**: Show feature importance chart, don't dive into RF math
3. **Show failures**: Dropped Bluetooth connection? Funny misclassification? Include it—makes it real
4. **Timestamps matter**: Let viewers jump to sections they care about
5. **End with actionable**: "You can build this too—here's the GitHub repo"

---

## **GitHub Repo Structure (for upload on Day 28)**

```
dog-mood-collar-vlog/
├── README.md (build guide + video link)
├── firmware/
│   └── dog_collar_firmware.ino
├── data/
│   ├── dog_sensor_data.csv (anonymized, 1000 samples)
│   └── collection_protocol.txt
├── ml/
│   ├── train_mood_model.py
│   ├── dog_mood_model.pkl (trained model)
│   └── feature_importance.json
├── app/
│   ├── flutter/ (mobile app source)
│   └── README.md (setup instructions)
├── hardware/
│   ├── BOM.csv
│   ├── wiring_diagram.svg
│   └── collar_housing.stl (3D model)
└── docs/
    ├── data_collection_protocol.md
    ├── TROUBLESHOOTING.md
    └── FUTURE_IMPROVEMENTS.md
```

---

## **Timeline at a Glance**

```
Week 1: Hardware ████░░░░░░ (Sensors arrive, firmware testing)
Week 2: Data ░░░░████░░░░░░░░ (Daily wear, 1000+ samples collected)
Week 3: ML+App ░░░░░░░░████░░░░ (Training, mobile app, testing)
Week 4: Vlog ░░░░░░░░░░░░░███░ (Filming, editing, publish)
```

---

## **Questions?**

If stuck:
1. Check TROUBLESHOOTING.md in repo
2. Post on r/arduino or r/esp32 with `[DOG COLLAR]` tag
3. Tag Claude in your notes for debugging help

**Good luck, Jaz! This is going to be awesome. 🐕💻**
