# TinyTalk (web app)

A phone app that connects straight to the collar, watches the cage with the phone's own camera, runs the mood model on the phone and says the phrase. No laptop is needed for live use or for recording; training still happens on a computer. It installs from the browser to the home screen and keeps working offline.

**Status:** a first version. The demo mode and the arithmetic are tested; **it has not been connected to a real collar or pointed at a real cage.**

| Check | Result |
|-------|--------|
| Features and mood probabilities match the Python scripts | Yes: `node app/check_parity.mjs`, 4 windows, largest probability error 1 × 10⁻⁸ |
| Demo mode in a browser: phrases, offline cache | Works |
| Camera tracker on made-up pictures: finds a dog-shaped blob, follows it, keeps it while still, survives a lamp switching on | Yes: `node app/check_camera.mjs` |
| Camera tab in a browser, fed a simulated picture in place of a camera | Works |
| A CSV written by the app is read by the Python trainer, with identical features | Yes |
| Bluetooth connection to a real collar | **Not tested** |
| Camera on a real phone, cage and dog | **Not tested** |
| Installed on a phone | **Not tested** |

## What it does

| Tab | Shows |
|-----|-------|
| **Talk** | The phrase for his mood, spoken aloud if you allow it. Buttons for "he just ate", "he just went potty" and "I'm leaving", which the model uses for hungry, potty and lonely. |
| **Camera** | The phone's camera watching the cage: takes the empty-cage picture, then follows his outline. His position, outline and movement go to the model. |
| **Record** | Tap a mood while you are sure of it; the collar and camera data are labelled with it. Saving downloads a CSV for the trainer. |
| **Collar** | Connect, battery, sensor health, dropped packets, and a demo. |

It applies the same rules as `ml/live_predict.py`: 8-second windows every 4 seconds, averaged over three, spoken only at 50% confidence or more, and the same mood repeated only after a minute.

## Limits

- **The model inside is the synthetic starter.** Its phrases are not real readings of your dog until you record your own data, train, and export (below). The app says so on screen.
- **Bluetooth needs Chrome or Edge** on Android, Windows, macOS or Linux. iPhone and iPad browsers do not support Web Bluetooth, so only the demo runs there.
- **Keep the screen on and the app in front.** Browsers stop Bluetooth for a page in the background.
- **The phone's camera and the laptop's are not interchangeable.** They measure the picture differently, so train a model on recordings made with the one you will use live.
- **Labelling is live only.** The app does not save video, so you cannot label afterwards as `ml/label_video.py` does. "Lonely" still needs the laptop's unattended recording, or a second person.
- **Recordings are held in memory** until you save. Save before closing the app.
- The demo plays made-up scenes from a simulated collar.

## Using the phone as the cage camera

1. Fix the phone so it sees the whole cage floor, and plug it in. It must not move afterwards.
2. Open the **Camera** tab and start the camera. With him out of the cage, take the empty-cage picture.
3. Put him back. A box should follow him, and stay on him when he lies still.
4. Connect the collar on the **Collar** tab. The **Talk** tab now uses both.

The pictures are analysed on the phone and never leave it. Retake the empty-cage picture whenever the phone, the cage or his bedding moves, or the phone is turned.

## Recording on the phone

1. Connect the collar, and start the camera if you want his position recorded.
2. On the **Record** tab, tap a mood while you are sure of it. Tap **Stop labelling** the moment you are not. Each stretch of one mood is a session; record every mood on several separate occasions.
3. Tap **Save recording**. Copy the downloaded `tinytalk-….csv` into `data/phone/` on your computer.
4. Train and export:

```bash
python ml/train_mood_model.py
```
```bash
python ml/export_app_model.py
```

The trainer reads everything in `data/phone/` alongside your other recordings.

## Put your own model in

After training on your own recordings:

```bash
python ml/export_app_model.py
```

That replaces `app/model.json`. Commit and push it, and the app picks it up on the next load.

## Run it on your computer

```bash
python -m http.server 8000 --directory app
```

Then open http://localhost:8000. Bluetooth and installing need either `localhost` or an `https` address.

## Files

| File | What it is |
|------|------------|
| `index.html`, `styles.css`, `app.js` | The page and its behaviour |
| `core.js` | Packet decoding, features, the forest and CSV rows; mirrors `ml/collar.py` and `ml/features.py` |
| `camera.js` | The dog finder; follows the steps of `ml/camera.py` |
| `cage.js`, `record.js` | The Camera and Record tabs |
| `model.json` | The exported Random Forest and the phrases |
| `sw.js`, `manifest.webmanifest`, `icons/` | What makes it installable and usable offline |
| `check_parity.mjs`, `check_camera.mjs`, `test/` | The checks |
