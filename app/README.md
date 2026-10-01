# TinyTalk (web app)

A phone app that connects straight to the collar, runs the mood model on the phone and says the phrase. No laptop is needed for live use. It installs from the browser to the home screen and keeps working offline.

**Status:** a first version. The demo mode and the arithmetic are tested; **it has not been connected to a real collar.**

| Check | Result |
|-------|--------|
| Features and mood probabilities match the Python scripts | Yes: `node app/check_parity.mjs`, 4 windows, largest probability error 1 × 10⁻⁸ |
| Demo mode in a browser: phrases, offline cache | Works |
| Bluetooth connection to a real collar | **Not tested** |
| Installed on a phone | **Not tested** |

## What it does

| Tab | Shows |
|-----|-------|
| **Talk** | The phrase for his mood, spoken aloud if you allow it. Buttons for "he just ate", "he just went potty" and "I'm leaving", which the model uses for hungry, potty and lonely. |
| **Collar** | Connect, battery, sensor health, dropped packets, and a demo. |

It applies the same rules as `ml/live_predict.py`: 8-second windows every 4 seconds, averaged over three, spoken only at 50% confidence or more, and the same mood repeated only after a minute.

## Limits

- **The model inside is the synthetic starter.** Its phrases are not real readings of your dog until you record your own data, train, and export (below). The app says so on screen.
- **Bluetooth needs Chrome or Edge** on Android, Windows, macOS or Linux. iPhone and iPad browsers do not support Web Bluetooth, so only the demo runs there.
- **Keep the screen on and the app in front.** Browsers stop Bluetooth for a page in the background.
- **No cage camera.** The app uses the collar only. A model trained with the camera will guess worse here; `export_app_model.py` warns you.
- **It does not record or label.** Use `ml/ble_data_logger.py` on a laptop for that.
- The demo plays made-up scenes from a simulated collar.

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
| `core.js` | Packet decoding, features and the forest; mirrors `ml/collar.py` and `ml/features.py` |
| `model.json` | The exported Random Forest and the phrases |
| `sw.js`, `manifest.webmanifest`, `icons/` | What makes it installable and usable offline |
| `check_parity.mjs`, `test/` | The check against Python |
