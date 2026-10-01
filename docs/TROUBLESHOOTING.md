# 🔧 Troubleshooting Guide

## Firmware Issues

### **Arduino IDE: "Board not recognized"**
- Check USB cable is properly connected
- Install CH340 driver (if using clone boards): https://github.com/JayHarkrider/CH340-Driver
- Select correct board: Tools > Board > ESP32 > ESP32 Dev Module
- Select correct port: Tools > Port > COM[X] (Windows) or /dev/ttyUSB0 (Linux)

### **Compilation Error: "Board selection was not specified"**
- Go to Tools > Board > Boards Manager
- Search "ESP32"
- Install "esp32 by Espressif Systems"
- Restart Arduino IDE

### **Serial Monitor Shows Gibberish**
- Wrong baud rate set
- Open Serial Monitor (Tools > Serial Monitor)
- Change baud rate to **115200** (bottom right)
- Should see "[INIT] Dog Mood Collar Firmware"

### **BLE Advertising Not Showing**
- Check firmware uploaded successfully (Serial Monitor shows init messages)
- Check phone BLE scanner app (iOS: BLE Scanner; Android: nRF Connect)
- If still not visible:
  - Power cycle ESP32 (unplug USB, wait 2 sec, plug back)
  - Check antenna isn't damaged (small PCB antenna on board)

### **Sensor Not Detected (Serial: "✗ MPU6050 Failed")**
- Check I2C wiring: SDA=21, SCL=22 on ESP32
- Check pull-up resistors (10kΩ recommended on SDA & SCL)
- Verify sensor address with I2C scanner:
  ```cpp
  #include <Wire.h>
  void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22);
    for (byte i = 8; i < 120; i++) {
      Wire.beginTransmission(i);
      if (Wire.endTransmission() == 0) {
        Serial.print("Found I2C device at address: 0x");
        Serial.println(i, HEX);
      }
    }
  }
  void loop() {}
  ```
- Common I2C addresses:
  - MPU6050: 0x68 or 0x69
  - MLX90614: 0x5A
  - MAX30102: 0x57

---

## Data Collection Issues

### **"Failed to find DogMood-Collar" (BLE Logger)**
- Ensure firmware is running (check Serial Monitor)
- Check phone is close to ESP32 (<10 meters)
- Restart phone Bluetooth
- Power cycle ESP32

### **BLE Data Not Streaming**
- Check `ble_data_logger.py` prerequisites installed:
  ```bash
  pip install bleak
  ```
- On Linux/Mac: Grant Bluetooth permissions
- On Windows: Enable Bluetooth in Settings
- Run with admin/sudo if permission errors

### **CSV File Not Created**
- Check folder permissions: `mkdir -p dog_sensor_data`
- Verify Python can write to disk
- Check file isn't open in Excel (locks file)

### **Mood Labels Not Syncing**
- Current version requires manual labeling (edit CSV after collection)
- Future version will add interactive CLI labeling
- Template: `timestamp, mood_label, confidence (1-5), notes`

---

## ML Training Issues

### **"No such file or directory: dog_sensor_data/sensor_readings.csv"**
- Ensure BLE logger has been run and CSV saved
- Check file location:
  ```bash
  ls -la dog_sensor_data/
  ```
- CSV should be in `dog_sensor_data/` folder

### **"ValueError: not enough values to unpack"**
- CSV columns don't match expected format
- Ensure CSV has headers:
  ```
  timestamp,mood_label,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,temp,heart_rate,bark_freq,bark_intensity
  ```
- Check no missing values (replace NaN with reasonable defaults)

### **"Memory Error" or Slow Training**
- Reduce `n_estimators` in Random Forest (from 150 to 50)
- On low-RAM systems:
  ```python
  rf_model = RandomForestClassifier(n_estimators=50, max_depth=10, n_jobs=1)
  ```

### **Model Accuracy <60%**
- Not enough training data (need 1000+ samples minimum)
- Imbalanced dataset (one mood has way more samples)
- Use `class_weight='balanced'` in RandomForestClassifier (already in code)
- Check manual mood labels are correct (garbage in = garbage out)

### **"ModuleNotFoundError: No module named 'sklearn'"**
- Install scikit-learn:
  ```bash
  pip install scikit-learn
  ```

---

## Power & Battery Issues

### **ESP32 Powers Off After 5 Minutes**
- LiPo battery depleted or faulty
- Check battery voltage: should be 3.7V when full, >3.0V when running
- TP4056 module LED status:
  - **Red:** Charging
  - **Blue:** Fully charged
  - **Off:** Power disconnected

### **Collar Gets Hot**
- Normal if just powered on (circuit stabilizing)
- If hot after 1 hour: possible short circuit
- Disconnect power and check solder joints

### **Can't Charge Battery**
- Check USB-C connector orientation (try flipping)
- Ensure micro-USB isn't swapped with USB-C
- Test with different USB power supply (1A minimum)

---

## 3D Printing & Housing

### **Collar Doesn't Fit Dog's Neck**
- Default STL is 40cm circumference
- Scale in Cura: Multiply by (desired_circumference / 40)
- Example: For 30cm neck → multiply by 0.75

### **Sensors Fall Out After Printing**
- Increase wall thickness in FreeCAD model
- Use epoxy or hot glue to secure sensors inside
- Add foam padding for vibration isolation

### **PETG Warping During Print**
- Increase bed temperature: 70–80°C (standard: 60°C)
- Use brim or skirt for better adhesion
- Ensure bed is level
- Reduce print speed if warping still occurs

---

## Mobile App Issues

### **"Could not find connected Bluetooth device"**
- Enable Bluetooth on phone
- Ensure collar is powered and BLE is broadcasting
- Check app has Bluetooth permission (granted at runtime)
- Restart app if disconnected suddenly

### **TensorFlow Lite Model Loading Error**
- Model file path is incorrect
- Ensure `dog_mood_model.tflite` is in app's assets folder
- Rebuild app after adding model:
  ```bash
  flutter clean
  flutter pub get
  flutter run
  ```

### **Low Inference Accuracy on Phone**
- Mobile version may differ from training environment
- Retrain with calibration samples from phone app
- Ensure feature scaling matches training pipeline

---

## Performance Optimization

### **Slow Data Collection (Firmware)**
- Current rate: 10 Hz (100ms per sample)
- If USB lag: reduce UART baud rate or batch data
- Check Serial Monitor doesn't slow BLE broadcasts

### **Training Takes >5 Minutes**
- Reduce tree depth: `max_depth=10` (instead of 15)
- Reduce estimators: `n_estimators=50` (instead of 150)
- Use subset for quick test: `X_train = X_train[:500]`

### **BLE Connection Drops Frequently**
- Increase advertising interval in firmware (currently 0.625s)
- Move ESP32 closer to phone
- Disable other Bluetooth devices nearby
- Check for WiFi interference (change WiFi channel)

---

## General Debugging Workflow

1. **Identify where problem occurs:**
   - Firmware? → Check Serial Monitor
   - Data collection? → Check CSV
   - ML training? → Check data + logs
   - App? → Check console output

2. **Enable verbose logging:**
   ```cpp
   // In firmware
   #define DEBUG 1
   #if DEBUG
     Serial.println("[DEBUG] Variable value: " + String(value));
   #endif
   ```

3. **Check hardware with multimeter:**
   - Battery voltage
   - 3.3V rail (should be exactly 3.3V)
   - I2C lines (should go high with pull-ups)

4. **Isolate the problem:**
   - Test sensors one at a time
   - Test BLE without sensors
   - Test ML with synthetic data first

5. **Search GitHub Issues:**
   - Most problems already solved: search esp32 + sensor name
   - MAX30102 common issue: reversed RED/IR LEDs

---

## When All Else Fails

1. **Restart everything:**
   - Power cycle ESP32 (disconnect USB for 5 sec)
   - Restart phone
   - Close and reopen apps

2. **Check for loose connections:**
   - Breadboard wires can slip out
   - Solder joints can crack

3. **Test with known-good setup:**
   - Use example Arduino sketches for each sensor
   - Confirm sensors work independently before integration

4. **Open an issue on GitHub:**
   - Include: error message, what you tried, hardware details
   - Attach Serial Monitor output
   - Reference this troubleshooting section

---

**Remember:** Most issues are solved by rebooting, checking connections, or examining error messages carefully.

Good luck, Boss! 🚀
