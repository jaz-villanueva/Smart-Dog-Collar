/*
 * Location beacon for the Smart Dog Collar (any ESP32 board)
 *
 * Plug one into a USB charger near each place that matters. The collar
 * reports how strongly it hears each beacon, which tells the model where
 * the dog is.
 *
 * Set BEACON_NAME before flashing each board:
 *   "DogMood-Bowl"  next to his food and water
 *   "DogMood-Door"  at the door he goes out through
 *   "DogMood-Bed"   beside his bed or crate
 */

#include <BLEDevice.h>

#define BEACON_NAME "DogMood-Bowl"

void setup() {
  BLEDevice::init(BEACON_NAME);

  BLEAdvertisementData advertisement;
  advertisement.setFlags(0x06);  // general discoverable, BLE only
  advertisement.setName(BEACON_NAME);

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->setAdvertisementData(advertisement);
  advertising->setScanResponse(false);
  advertising->setMinInterval(160);  // 100 ms, units of 0.625 ms
  advertising->setMaxInterval(240);  // 150 ms
  advertising->start();
}

void loop() {
  delay(1000);
}
