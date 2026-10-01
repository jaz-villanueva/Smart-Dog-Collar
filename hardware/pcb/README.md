# Carrier Board for the XIAO nRF52840 Sense

A small two-layer board that the XIAO solders onto. It replaces the loose battery wires and switch of the hand-wired build with something tidier and sturdier.

![Top of the carrier board](render_top.png)
![Bottom of the carrier board](render_bottom.png)

It is deliberately **not** a from-scratch board with its own radio chip. The XIAO already carries the processor, antenna, motion sensor, microphone and charger, tested and certified by its maker. This board only adds what the XIAO lacks.

## Status

| Check | Result |
|-------|--------|
| KiCad design rule check (KiCad 10.0.4) | 0 violations, 0 unconnected items; see [`drc_report.txt`](drc_report.txt) |
| Fabricated | **No** |
| Assembled and powered | **No** |
| Schematic file | None. The board is generated from [`generate_carrier.py`](generate_carrier.py), which lists every pad, net and track. The net table below is the schematic. |

The rule check confirms the copper matches the intended connections and meets clearance rules. It cannot confirm that the intended connections are right, or that the XIAO's pads are where the footprint says. **Order a small batch and run the checks under "Before you solder the battery" on the first board.**

## What it does

| Feature | Detail |
|---------|--------|
| Size | 28.6 × 21.9 mm, 0.8 mm thick, about 1 g bare (estimate) |
| Battery | Two plated holes for the LiPo's wires, marked `+` and `−` |
| Switch | Footprint for an SS12D00-type slide switch in the battery's positive lead |
| Battery pads | Plated holes under the XIAO's `BAT+`/`BAT−` pads, soldered from the back |
| Expansion | Four holes for a future I2C sensor: GND, 3V3, SCL, SDA |
| Antenna | No copper under the XIAO's antenna end |

## Connections

| Net | From | To |
|-----|------|----|
| `BAT_PLUS` | Battery `+` hole | Switch middle pin |
| `VBAT_SWITCHED` | Switch pin at the `ON` end | XIAO underside battery pad (pad 19, `VBAT`) |
| `GND` | Battery `−` hole, XIAO `GND` pin, XIAO underside pad 20, expansion `G` | Ground plane on the back |
| `+3V3` | XIAO `3V3` pin | Expansion `3` |
| `SDA` | XIAO `D4` | Expansion `A` |
| `SCL` | XIAO `D5` | Expansion `L` |

All other XIAO pins are soldered for mechanical strength only.

## Parts

| Ref | Part | Notes |
|-----|------|-------|
| U1 | Seeed XIAO nRF52840 Sense | Without header pins |
| SW1 | SS12D00 slide switch, 3 pins in a row, about 2.5 mm pitch | Common on Shopee as "SS12D00G3" |
| J1 | LiPo cell, 100–150 mAh, protected | Bare wire leads |
| J2 | Not fitted | For a future I2C sensor |

## Ordering

Upload the files in [`gerbers/`](gerbers/) as a zip to a board maker such as JLCPCB or PCBWay.

- Layers: 2
- Thickness: **0.8 mm** (lighter than the usual 1.6 mm)
- Everything else: defaults

No assembly service is needed; every part is hand-soldered.

## Assembly

1. **Switch.** Fit SW1 on the top, solder its three pins from the back, and trim them flush.
2. **XIAO.** Lay it on the top with its USB connector toward the edge with the four expansion holes, and its edge pads over the fourteen large pads. Tack one corner, check the alignment on both sides, then solder all fourteen.
3. **Battery pads.** Turn the board over. Feed solder into the two oval holes under the XIAO until it wets the XIAO's pad above each hole.
4. Stop here and run the checks below.
5. **Battery.** Solder the red lead into `+` and the black lead into `−`. Route the wires away from the end of the board with no copper, where the antenna is.

### Before you solder the battery

Use a multimeter on continuity or resistance:

- [ ] The `−` battery hole connects to the XIAO's `GND` pin.
- [ ] The `+` battery hole does **not** connect to `GND` with the switch in either position.
- [ ] With the switch at `ON`, the `+` hole connects to the oval hole **further from** the USB connector. With the switch at `OFF`, it does not.
- [ ] The oval hole **nearer** the USB connector connects to `GND`.

Then plug in USB with no battery: the XIAO should start normally. Only then solder the battery, and check its polarity with the multimeter first. A reversed LiPo can destroy the board and overheat.

If the `ON`/`OFF` labels turn out to be the wrong way round for your switch, that is harmless; just note it.

## Changing the design

Edit `generate_carrier.py`, then regenerate, fill the ground plane, and re-run the rule check:

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" generate_carrier.py
```
```bash
"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe" pcb drc --refill-zones --save-board --severity-all -o drc_report.txt dogmood_carrier.kicad_pcb
```

The board also opens directly in KiCad's PCB editor.

## Source of the XIAO dimensions

Pad positions and pin names come from Seeed Studio's published KiCad library, footprint and symbol `XIAO-nRF52840-SMD` (https://github.com/Seeed-Studio/OPL_Kicad_Library, retrieved 2026-10-01). The footprint here is drawn from those dimensions, with the two battery pads changed from surface pads to plated holes so they can be soldered by hand.
