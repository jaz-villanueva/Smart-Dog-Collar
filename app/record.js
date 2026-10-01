// The Record tab: label what he is doing while the collar (and camera) stream,
// then save a CSV in the layout ml/train_mood_model.py reads.

import { CSV_COLUMNS, csvRows } from './core.js';

const $ = (id) => document.getElementById(id);
const pad = (value) => String(value).padStart(2, '0');

let lines = [];
let mood = null;
let sessionId = null;
let sessions = 0;
let ready = false;           // true while a real collar is connected
const seconds = {};

function stamp(date) {
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-` +
    `${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

function show() {
  document.querySelectorAll('#moods button').forEach((button) => {
    button.disabled = !ready;
    button.setAttribute('aria-pressed', String(button.dataset.mood === mood));
    const recorded = Math.round(seconds[button.dataset.mood] || 0);
    button.querySelector('small').textContent = recorded ? `${recorded} s` : '';
  });
  $('pause').disabled = mood === null;
  $('save').disabled = $('discard').disabled = lines.length === 0;
  $('recorded').textContent = `${Math.round(lines.length / 50)} s`;
  $('record-state').textContent = !ready
    ? 'Connect the collar to record. The demo cannot be recorded.'
    : mood ? `Labelling as ${mood}. Tap "Stop labelling" the moment you are no longer sure.`
      : 'Tap a mood while you are sure that is how he feels.';
}

function setMood(next) {
  mood = next;
  if (mood) sessionId = `phone-${stamp(new Date())}-${++sessions}`;   // one session per stretch of one mood
  show();
}

/** Call for every packet from a real collar. */
export function record(packet, context) {
  if (!mood) return;
  lines.push(...csvRows(packet, context, sessionId, mood, new Date()));
  seconds[mood] = (seconds[mood] || 0) + 0.04;
}

/** Tell the tab whether a real collar is connected. */
export function setRecordable(connected) {
  ready = connected;
  if (!ready) mood = null;
  show();
}

export function setMoods(moods) {
  $('moods').replaceChildren(...moods.map((name) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.mood = name;
    button.append(name[0].toUpperCase() + name.slice(1), document.createElement('small'));
    button.addEventListener('click', () => setMood(name));
    return button;
  }));
  show();
}

function clear() {
  lines = [];
  mood = null;
  Object.keys(seconds).forEach((key) => delete seconds[key]);
  show();
}

$('pause').addEventListener('click', () => setMood(null));
$('save').addEventListener('click', () => {
  const file = new Blob([`${CSV_COLUMNS.join(',')}\n${lines.join('\n')}\n`], { type: 'text/csv' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(file);
  link.download = `tinytalk-${stamp(new Date())}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
  clear();
});
$('discard').addEventListener('click', () => {
  if (confirm('Throw away this recording?')) clear();
});
window.addEventListener('beforeunload', (event) => { if (lines.length) event.preventDefault(); });
setInterval(show, 1000);
