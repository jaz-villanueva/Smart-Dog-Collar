# Voice clips

One recorded clip for each phrase in [`ml/moods.json`](../../ml/moods.json), plus the out-of-range alarm. TinyTalk plays these in place of the phone's built-in voice, so he sounds the same on every phone. They play through whatever the phone is connected to, such as a Bluetooth speaker beside the cage.

| | |
|---|---|
| Clips | 21, about 21 seconds in total, 0.9 MB |
| Format | WAV, 22,050 Hz, mono, 16-bit |
| Made with | [Piper](https://github.com/OHF-Voice/piper1-gpl) 1.8.0, a free open-source speech engine that runs on your own computer |
| Voice | `en_US-ljspeech-medium`, a US English female voice, from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices), raised in pitch by 1.3 to sound small and young (about 306 Hz, against 214 Hz as recorded) |
| Voice licence | Its model card lists the training recordings (LJ Speech) as **public domain** |
| Cost | None. No account, plan or usage limit. |

**Status:** generated and checked for format and loudness. **Nobody has listened to them yet**; play a few before relying on them.

`index.json` maps each phrase to its clip. A phrase with no clip is spoken by the phone's own voice.

## Changing the phrases or the voice

Edit `ml/moods.json`, then record the clips again:

```bash
pip install piper-tts
```
```bash
python -m piper.download_voices en_US-ljspeech-medium
```
```bash
python ml/make_voice_clips.py --voice en_US-ljspeech-medium.onnx --pitch 1.3
```

`--pitch` sets how much higher than the voice as recorded: 1.0 leaves it alone, and larger is smaller and squeakier.

Other Piper voices whose model cards list public-domain or CC0 recordings: `en_US-kristin-medium` (female), `en_US-joe-medium`, `en_US-norman-medium` and `en_US-bryce-medium` (male). Check a voice's model card before using it; some, such as `en_US-ryan`, do not allow commercial use.

After changing the clips, add any new file names to the `VOICE` list in `../sw.js` so the app keeps them for offline use.
