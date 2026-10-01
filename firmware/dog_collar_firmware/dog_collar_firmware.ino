/*
 * Smart Dog Collar Firmware (ESP32)
 * Motion + sound sensing, streamed over BLE
 *
 * Hardware:
 * - ESP32-WROOM-32
 * - MPU6050 (IMU)        -> I2C (SDA=21, SCL=22)
 * - INMP441 (microphone) -> I2S (SD=32, WS=25, SCK=33, L/R=GND)
 *
 * Every 40 ms the collar sends one 43-byte notification (little-endian).
 * It carries two motion samples (50 Hz) and one sound frame (25 Hz):
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
 *
 * Band edges in Hz: 94, 156, 219, 312, 437, 625, 875, 1250, 1781, 2531,
 * 3594, 5094, 8000.
 *
 * 43 bytes needs a BLE MTU of at least 46. The collar offers 185; the
 * computer or phone must accept it (Windows, macOS, Linux and Android do).
 * ml/ble_data_logger.py decodes this layout; change both together.
 *
 * Libraries: Adafruit MPU6050 (pulls in Adafruit Unified Sensor + BusIO).
 */

#include <Wire.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <driver/i2s.h>
#include <math.h>

// ============== HARDWARE PINS ==============
#define I2C_SDA 21
#define I2C_SCL 22
#define MIC_SD  32
#define MIC_WS  25
#define MIC_SCK 33

// ============== SAMPLING ==============
#define AUDIO_RATE_HZ   16000
#define PACKET_RATE_HZ  25
#define FRAME_SAMPLES   (AUDIO_RATE_HZ / PACKET_RATE_HZ)  // 640 samples = 40 ms
#define HALF_SAMPLES    (FRAME_SAMPLES / 2)               // one IMU sample per half
#define HALF_MS         (500 / PACKET_RATE_HZ)
#define FFT_SIZE        512                               // 31.25 Hz per bin
#define NUM_BANDS       12

// First FFT bin of each band, plus the end of the last one
static const uint16_t BAND_EDGES[NUM_BANDS + 1] = {
  3, 5, 7, 10, 14, 20, 28, 40, 57, 81, 115, 163, 256
};

// ============== BLE ==============
#define DEVICE_NAME       "DogMood-Collar"
#define SERVICE_UUID      "12345678-1234-5678-1234-56789abcdef0"
#define SENSOR_CHAR_UUID  "87654321-4321-8765-4321-fedcba987654"
#define BLE_MTU           185

#define FLAG_IMU_OK 0x01
#define FLAG_MIC_OK 0x02

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
};
static_assert(sizeof(SensorPacket) == 43, "packet layout must match ble_data_logger.py");

Adafruit_MPU6050 mpu;
bool mpu_available = false;
bool mic_available = false;

BLEServer *pServer = NULL;
BLECharacteristic *pSensorChar = NULL;
volatile bool deviceConnected = false;
volatile bool restartAdvertising = false;

static int32_t rawAudio[FRAME_SAMPLES];
static float audio[FRAME_SAMPLES];
static float fftRe[FFT_SIZE];
static float fftIm[FFT_SIZE];
static float hannWindow[FFT_SIZE];

// ============== BLE CALLBACK ==============
class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer) {
    deviceConnected = true;
    Serial.println("[BLE] Device connected");
  }

  void onDisconnect(BLEServer *pServer) {
    deviceConnected = false;
    restartAdvertising = true;  // done from loop(), not from the BLE task
    Serial.println("[BLE] Device disconnected");
  }
};

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

// ============== SENSOR INIT ==============
bool initMicrophone() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = AUDIO_RATE_HZ;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;  // INMP441: 24-bit data in 32-bit slots
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;   // L/R pin to GND. Silent? Try ONLY_RIGHT.
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = 0;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = HALF_SAMPLES;
  cfg.use_apll = false;

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = MIC_SCK;
  pins.ws_io_num = MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = MIC_SD;

  if (i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL) != ESP_OK) return false;
  if (i2s_set_pin(I2S_NUM_0, &pins) != ESP_OK) return false;
  return true;
}

void initSensors() {
  Serial.println("[INIT] Starting sensor initialization...");

  Wire.begin(I2C_SDA, I2C_SCL);

  if (mpu.begin()) {
    mpu_available = true;
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    // 21 Hz low-pass keeps motion above the 25 Hz Nyquist limit from aliasing
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println("[MPU6050] OK (8G accel, 500 deg/s gyro)");
  } else {
    Serial.println("[MPU6050] FAILED - check wiring and address 0x68");
  }

  mic_available = initMicrophone();
  Serial.println(mic_available ? "[INMP441] OK (16 kHz I2S)" : "[INMP441] FAILED - I2S driver");

  for (int i = 0; i < FFT_SIZE; i++) {
    hannWindow[i] = 0.5f * (1.0f - cosf(2.0f * PI * i / (FFT_SIZE - 1)));
  }

  Serial.println("[INIT] Sensor initialization complete\n");
}

// ============== SENSOR READING ==============
void readImu(SensorPacket &p, int slot) {
  if (!mpu_available) return;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  ImuSample &s = p.imu[slot];
  s.ax = toInt16(a.acceleration.x * 100.0f);
  s.ay = toInt16(a.acceleration.y * 100.0f);
  s.az = toInt16(a.acceleration.z * 100.0f);
  s.gx = toInt16(g.gyro.x * RAD_TO_DEG * 10.0f);  // library reports rad/s
  s.gy = toInt16(g.gyro.y * RAD_TO_DEG * 10.0f);
  s.gz = toInt16(g.gyro.z * RAD_TO_DEG * 10.0f);
  p.flags |= FLAG_IMU_OK;
}

// Blocks until 20 ms of audio has arrived, which paces the main loop.
// Returns false if the microphone produced no data.
bool readAudioHalf(int half) {
  size_t wanted = HALF_SAMPLES * sizeof(int32_t);
  size_t bytesRead = 0;
  esp_err_t err = i2s_read(I2S_NUM_0, rawAudio + half * HALF_SAMPLES, wanted,
                           &bytesRead, pdMS_TO_TICKS(200));
  return err == ESP_OK && bytesRead == wanted;
}

void analyseAudio(SensorPacket &p) {
  // 24-bit sample sits in the top of the 32-bit slot; >> 14 leaves 18 bits
  float mean = 0.0f;
  for (int i = 0; i < FRAME_SAMPLES; i++) {
    audio[i] = (float)(rawAudio[i] >> 14);
    mean += audio[i];
  }
  mean /= FRAME_SAMPLES;

  float sumSq = 0.0f;
  for (int i = 0; i < FRAME_SAMPLES; i++) {
    audio[i] -= mean;  // remove the microphone's DC offset
    sumSq += audio[i] * audio[i];
  }
  float rms = sqrtf(sumSq / FRAME_SAMPLES);
  p.audio_rms = rms > 65535.0f ? 65535 : (uint16_t)rms;

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
}

// ============== BLE INIT ==============
void initBLE() {
  Serial.println("[BLE] Initializing BLE...");

  BLEDevice::init(DEVICE_NAME);
  BLEDevice::setMTU(BLE_MTU);
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);

  pSensorChar = pService->createCharacteristic(
    SENSOR_CHAR_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pSensorChar->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  BLEDevice::startAdvertising();

  Serial.println("[BLE] Advertising as " DEVICE_NAME);
}

// ============== SETUP ==============
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n====== Dog Mood Collar Firmware ======");
  Serial.println("Built: " __DATE__ " " __TIME__);
  Serial.println("=====================================\n");

  initSensors();
  initBLE();

  Serial.println("[SETUP] Ready. Waiting for BLE connection...\n");
}

// ============== MAIN LOOP ==============
void loop() {
  static uint16_t seq = 0;

  SensorPacket packet = {};
  packet.seq = seq++;

  bool gotAudio = true;
  for (int half = 0; half < 2; half++) {
    unsigned long halfStart = millis();
    bool ok = mic_available && readAudioHalf(half);
    gotAudio = gotAudio && ok;
    readImu(packet, half);

    // Without audio there is no blocking read, so pace the loop by the clock
    if (!ok) {
      unsigned long elapsed = millis() - halfStart;
      if (elapsed < HALF_MS) delay(HALF_MS - elapsed);
    }
  }
  if (gotAudio) analyseAudio(packet);

  if (deviceConnected) {
    pSensorChar->setValue((uint8_t *)&packet, sizeof(packet));
    pSensorChar->notify();
  }

  if (restartAdvertising) {
    restartAdvertising = false;
    delay(200);  // let the BLE stack finish the disconnect
    pServer->startAdvertising();
  }

  // Once a second, print a line for bench debugging
  if (packet.seq % PACKET_RATE_HZ == 0) {
    const ImuSample &s = packet.imu[1];
    Serial.printf("[DATA] seq=%u a=(%.2f,%.2f,%.2f) m/s2 g=(%.1f,%.1f,%.1f) deg/s rms=%u dom=%.0fHz flags=0x%02X\n",
                  packet.seq,
                  s.ax / 100.0f, s.ay / 100.0f, s.az / 100.0f,
                  s.gx / 10.0f, s.gy / 10.0f, s.gz / 10.0f,
                  packet.audio_rms, packet.dom_bin * 31.25f, packet.flags);
  }
}
