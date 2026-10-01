# Voice clips

One recorded clip for each phrase in [`ml/moods.json`](../../ml/moods.json), plus the out-of-range alarm. TinyTalk plays these in place of the phone's built-in voice, so he sounds the same on every phone. They play through whatever the phone is connected to, such as a Bluetooth speaker beside the cage.

| | |
|---|---|
| Clips | 21, about 33 seconds in total, 1.6 MB |
| Format | WAV, 24,000 Hz, mono, 16-bit |
| Voice | "little kid", a community voice on [Fish Audio](https://fish.audio/app/text-to-speech/?modelId=4888824c279e4ecc84dc7be337cbbc54), chosen by the owner |
| Made with | Fish Audio text to speech (S2.1 Pro, free plan), speed 1.3× |
| Delivery | Each phrase was given a tone tag to match its mood: `[excited]`, `[cheerful]`, `[sleepy]`, `[sad]`, `[worried]` or `[scared]` |
| Afterwards | The quicker of two takes was kept; silence trimmed, loudness evened out, and pitch raised by 1.08 (which also makes each clip 8% quicker), by [`ml/prepare_voice_clips.py`](../../ml/prepare_voice_clips.py) |

**Status:** generated and checked for format, length and loudness by measurement. The owner has heard the voice; **not every clip has been listened to**, so play them all once.

**Use:** these were made on Fish Audio's free plan for a personal, non-monetised project. Fish Audio voices are uploaded by its users, and who recorded this one is not known. Check Fish Audio's terms before using the clips for anything commercial.

`index.json` maps each phrase to its clip. A phrase with no clip is spoken by the phone's own voice.

## Changing a phrase

1. Edit `ml/moods.json`.
2. On Fish Audio, generate the new phrase with the same voice and download it.
3. Put it in a folder with the other clips, named after its place in `moods.json` (`playful_1.mp3` is the first playful phrase; the alarm is `lost_1.mp3`).
4. Prepare the clips:

```bash
pip install soundfile scipy
```
```bash
python ml/prepare_voice_clips.py my_clips --pitch 1.08
```

## A free voice with no account

[`ml/make_voice_clips.py`](../../ml/make_voice_clips.py) makes every clip on your own computer with Piper, an open-source speech engine, using a public-domain voice. It needs no account and has no usage limit or licence condition, but sounds less natural:

```bash
pip install piper-tts
```
```bash
python -m piper.download_voices en_US-ljspeech-medium
```
```bash
python ml/make_voice_clips.py --voice en_US-ljspeech-medium.onnx --pitch 1.3
```

After adding or renaming clips, update the `VOICE` list in `../sw.js` so the app keeps them for offline use.
