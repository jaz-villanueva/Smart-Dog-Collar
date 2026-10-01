# Wearable Build (for a teacup puppy)

The ESP32 breadboard build is for the bench. This is the version he wears. It is designed for a 4-month-old teacup puppy, so every choice below favours low weight and his safety over features.

**Status:** designed, not yet built. The weights and battery life below are estimates from typical part figures. Weigh the finished unit and measure the runtime before relying on them.

![Exploded view of the wearable](../docs/images/wearable_exploded.svg)

What to buy and where: [`docs/PH_SHOPPING_LIST.md`](../docs/PH_SHOPPING_LIST.md).

## Why there is no custom PCB

The idea of a custom PCB was to save weight. A ready-made board already does that better: the **Seeed XIAO nRF52840 Sense** is 21 × 18 mm and carries the processor, Bluetooth radio and antenna, a 6-axis motion sensor, a microphone and a LiPo charger. A custom board with the same parts would weigh about the same, cost more for a five-board minimum order, and add the risk of a first-time radio layout and fine-pitch assembly.

The only soldering is two battery wires and a switch.

### Optional carrier board

If you want it tidier than loose wires, [`pcb/`](pcb/) has a small two-layer carrier board that the XIAO solders onto. It holds the switch and the battery wires and adds about 1.5 g with the switch. It passes KiCad's design rule check but has not been fabricated yet. With the carrier, the housing grows to about 32 × 25 mm.

## Parts

| Part | Notes | Approx. weight |
|------|-------|----------------|
| Seeed XIAO nRF52840 **Sense** | The "Sense" version has the motion sensor and microphone. The plain version does not. | ~3 g |
| LiPo cell, 3.7 V, 100–150 mAh, with protection circuit | Sizes such as 401020 or 501225. Must have the small protection board under the tape. | ~3–4 g |
| Slide switch, sub-miniature | In the battery's positive lead | <1 g |
| Housing, TPU or PETG | Smooth, rounded, fully closed; see below | ~2–3 g |
| **Total** | | **~8–11 g** |

For comparison, the ESP32 dev board alone is about 10 g and a 1000 mAh cell about 20 g.

## What it measures

| Signal | Source | What it tells the model |
|--------|--------|-------------------------|
| Motion, 50 Hz | Built-in LSM6DS3TR-C | Activity, play, shaking, trembling, pacing, circling, stillness |
| Slow rocking while still | Same sensor | Resting breathing rate (experimental) |
| Sound, 12 bands at 25 Hz | Built-in PDM microphone | Barks, whines, growls, howls, panting |
| Battery voltage | Built-in divider | When to recharge |
| Time since meal and potty, owner away, hour | Typed into the logger | Hunger, potty need, loneliness |

Sensors deliberately left out:

- **Ultrasonic rangefinders (HC-SR04):** they emit 40 kHz, which dogs can hear, right beside his ears.
- **Optical heart-rate sensors (MAX30102):** they do not read through fur.
- **IR thermometer (MLX90614):** it reads the fur surface, not body temperature.
- **Chest-strap heart monitors:** made for human chests; too large and heavy for a teacup puppy.
- **On-collar speaker:** extra weight, and loud sound next to his ears. The phone or laptop speaks instead.

## Wiring

```
LiPo +  ──► slide switch ──► XIAO BAT+ pad (underside)
LiPo −  ──────────────────► XIAO BAT− pad (underside)
```

- Solder quickly with a fine tip; the pads are small and close to the shield.
- Insulate the joints with Kapton tape or a dab of hot glue so they cannot short on the shield can.
- Charge through the XIAO's USB-C port. The board charges the cell at a low rate suited to small cells.
- The switch isolates the battery for storage. Charging needs the switch **on**.

## Housing and mounting

![The wearable on a harness, on the dog's back](../docs/images/wearable_on_dog.svg)

- **Mount it on a harness, on his back between the shoulders, not on a neck collar.** That keeps the weight off his throat, and the sensor still picks up his movement and voice.
- Round every edge and leave nothing he can catch a tooth or claw on.
- Close the case completely so the battery cannot be reached; glue or screw it shut.
- Leave a 1–2 mm hole over the microphone, covered inside with a scrap of thin fabric.
- Pad the underside with soft fabric and check his skin and coat after each session.

## Safety rules

- **Supervised wear only.** Puppies chew, and a punctured LiPo cell can burn. Take it off when he is alone, crated or sleeping unattended.
- **Never charge it while he is wearing it.**
- Stop using it if the cell is swollen, dented or warm.
- Take it off if he scratches at it, freezes, or moves differently. A device he dislikes also spoils the data.
- He is growing: re-fit the harness every week or two.
- If you are unsure whether he can carry it, ask your vet before the first session.

## Flashing

1. Arduino IDE → Boards Manager → install **Seeed nRF52 Boards** (not the mbed-enabled package).
2. Library Manager → install **Seeed Arduino LSM6DS3**.
3. Board: **Seeed XIAO nRF52840 Sense**.
4. Open `firmware/dog_collar_xiao/dog_collar_xiao.ino` and upload.
5. Serial Monitor at 115200 should show `[IMU] OK`, `[MIC] OK`, then a `[DATA]` line each second.

If upload fails, double-tap the reset button to enter the bootloader and try again.

## Expected battery life (unmeasured)

The nRF52840 with the microphone and 25 packets a second should average under 10 mA, which would give a 150 mAh cell more than 12 hours. Measure it: the logger's `?` command shows the battery voltage. Recharge at about 3.5 V.
