# Starter Dataset (Synthetic)

**No dog was involved.** `synthetic_starter.csv.gz` is simulated by [`ml/make_starter_dataset.py`](../../ml/make_starter_dataset.py) from hand-written guesses at what each mood looks like to the collar. It is here so the trainer and the live script can be run before the first real recording, and to show the CSV layout the logger writes.

| | |
|---|---|
| Rows | 120,000 (40 minutes at 50 Hz) |
| Sessions | 60: 6 per mood, 40 seconds each |
| Columns | The same as `data/sensor_readings.csv` from `ble_data_logger.py` |
| Camera and heart-rate columns | Blank |

## The starter model

[`ml/starter_model/`](../../ml/starter_model/) was trained on this file with scikit-learn 1.9.1:

```bash
python ml/train_mood_model.py --data data/starter/synthetic_starter.csv.gz --out ml/starter_model
```

It scores 99.3% on held-out synthetic sessions. That figure only shows the simulated moods were made easy to tell apart. **It is not an estimate of accuracy on a real dog**, and the model's guesses on a real collar are meaningless.

To watch the live script run with it:

```bash
python ml/live_predict.py --model-dir ml/starter_model --mute
```

If the model fails to load, your scikit-learn version differs; retrain with the command above.

## Adding your own data

Your recordings go to `data/sensor_readings.csv` (live labels) and `data/recordings/` (labelled from video). The trainer reads only those by default, so the synthetic rows never mix with real ones:

```bash
python ml/train_mood_model.py
```

That writes your model to `ml/trained_models/`, which `live_predict.py` uses by default.
