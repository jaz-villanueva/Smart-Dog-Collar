/*
 * Smart Dog Collar Firmware (Seeed XIAO nRF52840 Sense) - the wearable version
 * Motion + sound sensing, streamed over BLE
 *
 * The XIAO nRF52840 Sense carries everything on one 21 x 18 mm board:
 * - nRF52840 (Bluetooth LE)
 * - LSM6DS3TR-C 6-axis IMU
 * - PDM microphone
 * - LiPo charger (battery solders to the BAT+/BAT- pads underneath)
 *
 * Every 40 ms the collar sends one 44-byte notification (little-endian),
 * the same packet as firmware/dog_collar_firmware:
 *
 *   offset  type       field        unit
 *   0       uint16     seq          packet counter, wraps at 65535
 *   2       int16 x3   accel A      0.01 m/s^2, first half of the frame
 *   8       int16 x3   gyro A       0.1 deg/s
 *   14      int16 x3   accel B      second half of the frame
 *   20      int16 x3   gyro B
 *   26      uint16     audio_rms    loudness of the frame (0-65535)
 *   28      uint8      dom_bin      loudest frequency, x 31.25 Hz
 *   29      uint8      zcr          zero crossings in 512 samples, / 2
 *   30      uint8      flags        bit0 = IMU ok, bit1 = mic ok
 *   31      uint8 x12  bands        8 * log2(1 + mean magnitude) per band
 *   43      uint8      battery      x 0.02 V; 0 = not measured
 *
 * ml/collar.py decodes this layout; change all three together.
 *
 * Arduino setup:
 * - Boards Manager: "Seeed nRF52 Boards" (not the mbed-enabled package)
 * - Board: "Seeed XIAO nRF52840 Sense"
 * - Library: "Seeed Arduino LSM6DS3"
 */

#include <bluefruit.h>
#include <LSM6DS3.h>
#include <PDM.h>
#include <Wire.h>
#include <math.h>

// ============== SAMPLING ==============
#define AUDIO_RATE_HZ   16000
#define IMU_PERIOD_MS   20                                 // 50 Hz motion
#define FRAME_SAMPLES   640                                // 40 ms of sound
#define FFT_SIZE        512                                // 31.25 Hz per bin
#define NUM_BANDS       12
#define RING_SIZE       2048                               // power of two, > FRAME_SAMPLES

// First FFT bin of each band, plus the end of the last one
static const uint16_t BAND_EDGES[NUM_BANDS + 1] = {
  3, 5, 7, 10, 14, 20, 28, 40, 57, 81, 115, 163, 256
};

// ============== BATTERY ==============
// The XIAO reads its battery through a divider on P0.31, switched by P0.14.
// P0.14 must stay LOW: driving it HIGH while charging can damage P0.31.
#define BATTERY_DIVIDER   (1510.0f / 510.0f)
#define BATTERY_PERIOD_MS 10000

// ============== BLE ==============
#define DEVICE_NAME "DogMood-Collar"
// 12345678-1234-5678-1234-56789abcdef0, least significant byte first
static const uint8_t SERVICE_UUID[16] = {
  0xf0, 0xde, 0xbc, 0x9a, 0x78, 0x56, 0x34, 0x12,
  0x78, 0x56, 0x34, 0x12, 0x78, 0x56, 0x34, 0x12
};
// 87654321-4321-8765-4321-fedcba987654, least significant byte first
static const uint8_t SENSOR_CHAR_UUID[16] = {
  0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe, 0x21, 0x43,
  0x65, 0x87, 0x21, 0x43, 0x21, 0x43, 0x65, 0x87
};

#define FLAG_IMU_OK 0x01
#define FLAG_MIC_OK 0x02
#define GRAVITY     9.80665f

struct __attribute__((packed)) ImuSample {
  int16_t ax, ay, az;
  int16_t gx, gy, gz;
};

struct __attribute__((packed)) SensorPacket {
  uint16_t seq;
  ImuSample imu[2];
  uint16_t audio_rms;
  uint8_t dom_bin;
  uint8_t zcr;
  uint8_t flags;
  uint8_t bands[NUM_BANDS];
  uint8_t battery;
};
static_assert(sizeof(SensorPacket) == 44, "packet layout must match ml/collar.py");

LSM6DS3 imu(I2C_MODE, 0x6A);
BLEService collarService(SERVICE_UUID);
BLECharacteristic sensorChar(SENSOR_CHAR_UUID);

bool imu_available = false;
bool mic_available = false;

// Filled by the microphone interrupt, read by loop()
static int16_t audioRing[RING_SIZE];
static volatile uint32_t audioWritten = 0;

static float audio[FRAME_SAMPLES];
static float fftRe[FFT_SIZE];
static float fftIm[FFT_SIZE];
static float hannWindow[FFT_SIZE];

static uint8_t batteryLevel = 0;

// ============== HELPERS ==============
static int16_t toInt16(float v) {
  if (v > 32767.0f) return 32767;
  if (v < -32768.0f) return -32768;
  return (int16_t)lroundf(v);
}

static uint8_t toUint8(float v) {
  if (v > 255.0f) return 255;
  if (v < 0.0f) return 0;
  return (uint8_t)lroundf(v);
}

// In-place radix-2 FFT
static void fft(float *re, float *im, int n) {
  for (int i = 1, j = 0; i < n; i++) {
    int bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      float t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (int len = 2; len <= n; len <<= 1) {
    float ang = -2.0f * PI / len;
    float wr = cosf(ang), wi = sinf(ang);
    for (int i = 0; i < n; i += len) {
      float cr = 1.0f, ci = 0.0f;
      for (int k = 0; k < len / 2; k++) {
        int a = i + k, b = a + len / 2;
        float xr = re[b] * cr - im[b] * ci;
        float xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr; im[b] = im[a] - xi;
        re[a] += xr;        im[a] += xi;
        float ncr = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = ncr;
      }
    }
  }
}

// ============== MICROPHONE ==============
// Runs in interrupt context: only copy samples into the ring buffer
void onPdmData() {
  static int16_t chunk[256];
  int bytes = PDM.available();
  if (bytes > (int)sizeof(chunk)) bytes = sizeof(chunk);
  PDM.read(chunk, bytes);

  uint32_t written = audioWritten;
  for (int i = 0; i < bytes / 2; i++) {
    audioRing[written & (RING_SIZE - 1)] = chunk[i];
    written++;
  }
  audioWritten = written;
}

// Analyse the most recent 40 ms of sound. Returns false if none has arrived.
bool analyseAudio(SensorPacket &p) {
  uint32_t written = audioWritten;
  if (written < FRAME_SAMPLES) return false;

  float mean = 0.0f;
  for (int i = 0; i < FRAME_SAMPLES; i++) {
    audio[i] = (float)audioRing[(written - FRAME_SAMPLES + i) & (RING_SIZE - 1)];
    mean += audio[i];
  }
  mean /= FRAME_SAMPLES;

  float sumSq = 0.0f;
  for (int i = 0; i < FRAME_SAMPLES; i++) {
    audio[i] -= mean;  // remove the microphone's DC offset
    sumSq += audio[i] * audio[i];
  }
  p.audio_rms = (uint16_t)sqrtf(sumSq / FRAME_SAMPLES);

  int crossings = 0;
  for (int i = 1; i < FFT_SIZE; i++) {
    if ((audio[i - 1] < 0.0f) != (audio[i] < 0.0f)) crossings++;
  }
  p.zcr = toUint8(crossings / 2.0f);

  for (int i = 0; i < FFT_SIZE; i++) {
    fftRe[i] = audio[i] * hannWindow[i];
    fftIm[i] = 0.0f;
  }
  fft(fftRe, fftIm, FFT_SIZE);

  float peak = 0.0f;
  int peakBin = 0;
  for (int band = 0; band < NUM_BANDS; band++) {
    float sum = 0.0f;
    for (int bin = BAND_EDGES[band]; bin < BAND_EDGES[band + 1]; bin++) {
      float mag = sqrtf(fftRe[bin] * fftRe[bin] + fftIm[bin] * fftIm[bin]);
      sum += mag;
      if (mag > peak) { peak = mag; peakBin = bin; }
    }
    float meanMag = sum / (BAND_EDGES[band + 1] - BAND_EDGES[band]);
    p.bands[band] = toUint8(8.0f * log2f(1.0f + meanMag));
  }
  p.dom_bin = (uint8_t)peakBin;
  p.flags |= FLAG_MIC_OK;
  return true;
}

// ============== MOTION ==============
void readImu(SensorPacket &p, int slot) {
  if (!imu_available) return;

  ImuSample &s = p.imu[slot];
  s.ax = toInt16(imu.readFloatAccelX() * GRAVITY * 100.0f);  // library reports g
  s.ay = toInt16(imu.readFloatAccelY() * GRAVITY * 100.0f);
  s.az = toInt16(imu.readFloatAccelZ() * GRAVITY * 100.0f);
  s.gx = toInt16(imu.readFloatGyroX() * 10.0f);              // library reports deg/s
  s.gy = toInt16(imu.readFloatGyroY() * 10.0f);
  s.gz = toInt16(imu.readFloatGyroZ() * 10.0f);
  p.flags |= FLAG_IMU_OK;
}

// ============== BATTERY ==============
void readBattery() {
  float volts = analogRead(PIN_VBAT) * (2.4f / 4096.0f) * BATTERY_DIVIDER;
  batteryLevel = toUint8(volts / 0.02f);
}

// ============== BLE ==============
void initBLE() {
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);  // allows the 44-byte packet
  Bluefruit.begin(1, 0);                         // one connection, as a peripheral
  Bluefruit.setName(DEVICE_NAME);
  Bluefruit.setTxPower(0);

  collarService.begin();
  sensorChar.setProperties(CHR_PROPS_NOTIFY);
  sensorChar.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
  sensorChar.setFixedLen(sizeof(SensorPacket));
  sensorChar.begin();

  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addService(collarService);
  Bluefruit.ScanResponse.addName();
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.setInterval(160, 244);   // units of 0.625 ms
  Bluefruit.Advertising.start(0);
}

// ============== SETUP ==============
void setup() {
  Serial.begin(115200);

  for (int i = 0; i < FFT_SIZE; i++) {
    hannWindow[i] = 0.5f * (1.0f - cosf(2.0f * PI * i / (FFT_SIZE - 1)));
  }

  pinMode(VBAT_ENABLE, OUTPUT);
  digitalWrite(VBAT_ENABLE, LOW);
  analogReference(AR_INTERNAL_2_4);
  analogReadResolution(12);
  readBattery();

  imu_available = imu.begin() == 0;

  PDM.onReceive(onPdmData);
  mic_available = PDM.begin(1, AUDIO_RATE_HZ);

  initBLE();

  Serial.println("\n====== Dog Mood Collar (XIAO) ======");
  Serial.println(imu_available ? "[IMU] OK" : "[IMU] FAILED");
  Serial.println(mic_available ? "[MIC] OK" : "[MIC] FAILED");
  Serial.println("[BLE] Advertising as " DEVICE_NAME);
}

// ============== MAIN LOOP ==============
void loop() {
  static uint16_t seq = 0;
  static uint32_t nextImuMs = 0;
  static uint32_t nextBatteryMs = 0;
  static int slot = 0;
  static SensorPacket packet = {};

  uint32_t now = millis();
  if ((int32_t)(now - nextImuMs) < 0) {
    delay(1);
    return;
  }
  nextImuMs += IMU_PERIOD_MS;
  if ((int32_t)(now - nextImuMs) > 100) nextImuMs = now + IMU_PERIOD_MS;  // fell behind

  readImu(packet, slot);
  if (++slot < 2) return;

  // Two motion samples collected: finish the packet and send it
  slot = 0;
  packet.seq = seq++;
  if (mic_available) analyseAudio(packet);
  packet.battery = batteryLevel;

  if (Bluefruit.connected()) {
    sensorChar.notify(&packet, sizeof(packet));
  }

  if (packet.seq % 25 == 0) {
    Serial.printf("[DATA] seq=%u rms=%u dom=%.0fHz batt=%.2fV flags=0x%02X\n",
                  packet.seq, packet.audio_rms, packet.dom_bin * 31.25f,
                  packet.battery * 0.02f, packet.flags);
  }

  if ((int32_t)(now - nextBatteryMs) >= 0) {
    nextBatteryMs = now + BATTERY_PERIOD_MS;
    readBattery();
  }

  packet = {};
}
