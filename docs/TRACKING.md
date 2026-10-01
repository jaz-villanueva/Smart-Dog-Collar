# Tracking

What this collar can and cannot tell you about where he is.

| Question | Answer | How |
|----------|--------|-----|
| Which spot in the home is he at? | Yes, roughly | `ml/track.py`, from the three beacons |
| Where did he spend his time today? | Yes | `data/track_log.csv`, written by `track.py` |
| Has he left Bluetooth range? | Yes | `track.py` raises an alarm |
| Where is he on a map, outdoors? | **No** | Needs hardware this collar does not have; see below |

**Status:** `track.py` is written and tested with simulated beacon signals. It has not been run against a real collar or real beacons.

## Indoor tracking

It needs the beacons from [`hardware/WEARABLE_BUILD.md`](../hardware/WEARABLE_BUILD.md): three ESP32 boards named `DogMood-Bowl`, `DogMood-Door` and `DogMood-Bed`. No extra hardware goes on the dog.

```bash
python ml/track.py
```

```
[14:02:10] He is at his bed  (bowl -85, door -80, bed -52 dBm)
[14:20:44] He is not near any beacon  (bowl -82, door -83, bed -77 dBm)
[14:21:30] He is at his door  (bowl -80, door -57 dBm)
[14:25:02] OUT OF RANGE: the collar cannot be heard. It is switched off, flat, or more than about 10 m away.
```

How it decides:

| Step | Rule |
|------|------|
| Smooth | Median signal strength of each beacon over the last 3 seconds; a beacon heard less than half that time is ignored |
| Near | He is "at" the strongest beacon if it is −70 dBm or stronger; otherwise "not near any beacon" |
| Hold | Once at a beacon, another must be 6 dB stronger to take over, so he does not flicker between two |
| Lost | No packets for 5 seconds, or a dropped connection, raises the alarm; the script keeps trying to reconnect |

Every visit is added to `data/track_log.csv` with the time he arrived, the time he left, the place and the seconds spent there.

### Tuning

Signal strength depends on your walls, the beacon boards and how he is standing, so −70 dBm is only a starting point. Hold the collar beside each beacon, read the numbers the script prints, then walk two metres away and read them again. Pick a value between the two:

```bash
python ml/track.py --near -65
```

### Limits

- It says which beacon he is nearest, to within a metre or two at best. It does not give a position in the room.
- His body blocks the signal, so the reading changes when he turns round.
- It covers three spots. More spots need more beacon names in the firmware and in `ml/collar.py`.
- The laptop must be within Bluetooth range of the collar, about 10 m and less through walls.
- The alarm means "the laptop cannot hear the collar". It cannot tell a dog that has left from a flat battery.

## Outdoors, or a lost dog

This collar cannot do it, and software cannot add it. Finding a dog outside the home needs two things the collar lacks: a way to know its position, and a way to send that position over a long distance.

| Option | What it takes | Verdict for a teacup puppy |
|--------|---------------|----------------------------|
| Ready-made Bluetooth tag on the harness (AirTag, Galaxy SmartTag or similar) | Nothing to build. About 10 g. Located by other people's phones passing nearby. | **The practical choice.** Works in towns; poor where few phones pass. |
| Ready-made pet GPS tracker | A subscription. Usually 25 g or more. | Too heavy for him now; reasonable for a larger dog. |
| GPS module on this collar | A u-blox module with an I2C port could use the carrier board's expansion holes. Adds weight and an antenna, and cuts battery life sharply. Firmware for it is **not written**. | Not worth it: the position still only reaches a laptop 10 m away. |
| GPS plus a cellular or LoRa link | A different, larger device with its own board, antenna and battery | Not this project. |

The collar and a tag do different jobs and can share the harness: the collar for mood and where he is in the home, the tag for finding him if he gets out.
