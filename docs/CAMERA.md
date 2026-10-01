# Cage Camera

A fixed camera on his cage is how the system knows where he is. It adds two things the wearable cannot give:

1. **What he looks like from outside:** where he is in the cage, whether his outline is long and low (lying) or tall (sitting, standing), and how much he is moving.
2. **A way to label afterwards.** The logger records everything with video while you are away, and you label the video later. This is the only honest way to collect "lonely" data, and it is easier than typing labels live.

**Status:** written and tested on a synthetic video (a dark shape moving across a plain background). Not yet run on a real camera or a real dog.

Two cameras can do this job:

| Camera | Runs on | Use it when |
|--------|---------|-------------|
| USB webcam or Wi-Fi camera | The laptop, with the Python scripts below | You want video saved so you can label afterwards |
| A phone, in the TinyTalk app | The phone itself; see [`app/README.md`](../app/README.md) | You want live moods with no laptop |

The two measure the picture differently, so a model must be trained on recordings from the camera it will use live.

## What it does not do

- **No tail, ear or face tracking.** It sees an outline, not body parts. Those need an animal pose model such as DeepLabCut's quadruped model, which is the next step and is not built.
- **Only in the cage.** Outside the camera's view those columns are blank and the model falls back on the wearable.
- **It needs contrast.** A cream puppy on cream bedding will be hard to see. Bedding in a colour unlike his coat helps a lot.
- **It needs steady lighting.** A lamp switching on or off is handled. A camera switching to infrared night vision changes the whole picture, and the tracker then reports nothing until you take a new empty-cage picture in that mode.

## Setup

1. **Mount the camera** above and slightly in front of the cage so it sees the whole floor. Fix it firmly: if the camera or cage moves, the tracker has to start again. Keep the camera and its cable outside the cage, out of his reach.
2. **Find its source.** A USB webcam is usually `0` (or `1` if the laptop has its own). A Wi-Fi camera needs its stream address, for example `rtsp://user:password@192.168.1.50/stream1`; check the camera's manual.
3. **Take the empty-cage picture** with him out of the cage:
   ```bash
   python ml/camera.py --camera 0 --save-background
   ```
   Retake it whenever you move the camera, the cage, or his bedding.
4. **Check the tracker.** Put him back and run:
   ```bash
   python ml/camera.py --camera 0
   ```
   A box should follow him, and stay on him when he lies still. If the box is missing or covers the whole picture, improve the contrast or lighting and retake the empty-cage picture.

Without an empty-cage picture the tracker still runs, but it only sees him while he moves.

## Recording now, labelling later

```bash
python ml/ble_data_logger.py --camera 0 --unattended
```

This saves a folder under `data/recordings/` with the collar data, the video and the time of every frame. Type `away` as you leave and `home` when you return, `fed` and `went` as usual, and `q` to stop. The laptop must stay within Bluetooth range of him.

Then label it:

```bash
python ml/label_video.py
```

| Key | Action |
|-----|--------|
| `1`–`9`, `0` | Mark his mood from this frame onward (the list is on screen) |
| `u` | Erase labels from this frame onward |
| `k` | Stop marking; keep what is there |
| space | Pause / resume |
| `a` / `d` | Back / forward 5 seconds |
| `-` / `+` | Slower / faster |
| `q` | Save and quit |

Playing the video changes nothing until you press a mood key, so you can watch first and label on a second pass. Only label the stretches you are sure about. Your progress is saved, so you can reopen a recording and continue.

The trainer picks up every labelled recording automatically:

```bash
python ml/train_mood_model.py
```

## Labelling live with the camera

If you are watching him yourself, add the camera to the normal logger and type moods as before:

```bash
python ml/ble_data_logger.py --camera 0
```

## Live moods with the camera

```bash
python ml/live_predict.py --camera 0
```

A model trained with camera data expects the camera at prediction time; the script warns you if it is missing.

## What the camera adds to each row

| Column | Meaning |
|--------|---------|
| `cam_x`, `cam_y` | Centre of his outline, as a fraction of the picture (0–1) |
| `cam_w`, `cam_h` | Width and height of his outline |
| `cam_area` | How much of the picture he fills |
| `cam_motion` | How much of the picture changed since the previous frame |

From these the model gets his average position, how far he travelled, his outline's shape, and how restless he is over each 8-second window.

## Privacy

The video shows the inside of your home. `data/recordings/` is excluded from git, so recordings are never pushed. Keep a Wi-Fi camera on your home network only; do not open its stream to the internet.
