// Checks that the app computes the same features and mood probabilities as Python.
//
//   python ml/export_app_model.py --model-dir ml/starter_model --synthetic \
//       --sample data/starter/synthetic_starter.csv.gz
//   node app/check_parity.mjs

import { readFileSync } from 'node:fs';
import { predictProba, windowFeatures } from './core.js';

const here = new URL('.', import.meta.url);
const model = JSON.parse(readFileSync(new URL('model.json', here)));
const windows = JSON.parse(readFileSync(new URL('test/parity_sample.json', here)));

let worstFeature = 0, worstProba = 0, failed = false;
for (const window of windows) {
  const features = windowFeatures(window.packets, window.context);
  for (const name of model.feature_names) {
    const error = Math.abs(features[name] - window.features[name]) / Math.max(1, Math.abs(window.features[name]));
    if (!(error < 1e-6)) {
      failed = true;
      console.log(`  ${window.mood}: ${name} = ${features[name]}, Python has ${window.features[name]}`);
    }
    worstFeature = Math.max(worstFeature, error);
  }
  const proba = predictProba(model, features);
  const error = Math.max(...proba.map((p, i) => Math.abs(p - window.proba[i])));
  if (!(error < 1e-3)) failed = true;
  worstProba = Math.max(worstProba, error);
  const best = model.classes[proba.indexOf(Math.max(...proba))];
  console.log(`${window.mood.padEnd(9)} -> ${best.padEnd(9)} ${(Math.max(...proba) * 100).toFixed(1)}%`);
}
console.log(`${windows.length} windows; largest feature error ${worstFeature.toExponential(1)}, ` +
  `largest probability error ${worstProba.toExponential(1)}`);
console.log(failed ? 'MISMATCH' : 'OK: the app matches Python');
process.exit(failed ? 1 : 0);
