// TinyTalk: connects to the collar over Web Bluetooth, runs the mood model on
// the phone, and says the phrase. The arithmetic lives in core.js.

import {
  DEVICE_NAME, MoodPredictor, NUM_BANDS, PACKET_SIZE, SENSOR_CHAR_UUID, SERVICE_UUID, decodePacket,
} from './core.js';
import { cameraOn, currentCam } from './cage.js';
import { record, setMoods, setRecordable } from './record.js';

const DOG = 'Tiny';
const REPEAT_MS = 60_000;      // say the same mood again only after this long
const LOST_MS = 5_000;         // no packets for this long means out of range
const RETRY_MS = 5_000;
const HISTORY_LENGTH = 8;

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- Saved state

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window */ }
}

const context = load('context', { lastFed: null, lastPotty: null, ownerAway: false });

// ---------------------------------------------------------------- Session

let model = null;
let predictor = null;
let device = null;
let demoTimer = null;
let wakeLock = null;
let lastPacketAt = 0;
let lost = false;
let lastSeq = null;
let received = 0;
let dropped = 0;
let spoken = { mood: null, at: 0 };
let latest = null;

function minutesSince(stamp) {
  return stamp === null ? null : Math.round((Date.now() - stamp) / 6000) / 10;
}

function currentContext() {
  if (demoTimer) return demoContext();
  return {
    hour: new Date().getHours(),
    minsSinceFed: minutesSince(context.lastFed),
    minsSincePotty: minutesSince(context.lastPotty),
    ownerAway: context.ownerAway,
  };
}

function onPacket(packet) {
  lastPacketAt = Date.now();
  if (lost) { lost = false; setStatus(demoTimer ? 'Demo' : 'Connected', 'on'); }
  if (lastSeq !== null) dropped += ((packet.seq - lastSeq - 1) & 0xffff);
  lastSeq = packet.seq;
  received++;
  latest = packet;

  const now = currentContext();
  packet.cam = demoTimer ? null : currentCam();
  if (!demoTimer) record(packet, now);
  const result = predictor ? predictor.add(packet, now) : null;
  if (result) showMood(result);
}

// ---------------------------------------------------------------- Mood

// Recorded clips of each phrase (see ml/make_voice_clips.py), so he always has
// the same voice. A phrase without a clip falls back to the phone's own voice.
const clips = {};
let playing = null;

fetch('voice/index.json').then((response) => response.json()).then((index) => {
  for (const [phrase, file] of Object.entries(index)) {
    clips[phrase] = new Audio(`voice/${file}`);
    clips[phrase].preload = 'auto';
  }
}).catch(() => {});

function say(text) {
  if (!$('speak').checked) return;
  playing?.pause();
  if (clips[text]) {
    playing = clips[text];
    playing.currentTime = 0;
    playing.play().catch(() => {});
  } else if ('speechSynthesis' in window) {
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}

function showMood({ mood, confidence, sure }) {
  const percent = `${Math.round(confidence * 100)}%`;
  if (!sure) {
    $('mood-detail').textContent = `Not sure. Best guess: ${mood}, ${percent}.`;
    return;
  }
  const now = Date.now();
  if (mood === spoken.mood && now - spoken.at < REPEAT_MS) {
    $('mood-detail').textContent = `${mood}, ${percent} sure`;
    return;
  }
  const choices = model.phrases[mood];
  const phrase = choices[Math.floor(Math.random() * choices.length)];
  spoken = { mood, at: now };
  $('bubble').classList.remove('quiet');
  $('phrase').textContent = phrase;
  $('mood-detail').textContent = `${mood}, ${percent} sure`;
  say(phrase);

  const item = document.createElement('li');
  const time = document.createElement('time');
  time.textContent = new Date(now).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  item.append(phrase, time);
  const list = $('history');
  list.querySelector('.empty')?.remove();
  list.prepend(item);
  while (list.children.length > HISTORY_LENGTH) list.lastChild.remove();
}

function quietBubble(text, detail = '') {
  $('bubble').classList.add('quiet');
  $('phrase').textContent = text;
  $('mood-detail').textContent = detail;
}

// ---------------------------------------------------------------- Status

function setStatus(text, kind = '') {
  $('status').textContent = text;
  $('status').className = `pill ${kind}`.trim();
}

function describeSince(stamp) {
  const minutes = minutesSince(stamp);
  if (minutes === null) return '';
  if (minutes < 1) return 'just now';
  return minutes < 60 ? `${Math.round(minutes)} min ago` : `${Math.floor(minutes / 60)} h ${Math.round(minutes % 60)} m ago`;
}

function showContext() {
  $('since-fed').textContent = describeSince(context.lastFed);
  $('since-potty').textContent = describeSince(context.lastPotty);
  $('away-button').setAttribute('aria-pressed', String(context.ownerAway));
  $('away-button').textContent = context.ownerAway ? "I'm back" : "I'm leaving";
}

function refresh() {
  $('packets').textContent = received.toLocaleString();
  $('dropped').textContent = dropped.toLocaleString();
  if (latest) {
    $('battery').textContent = latest.battery ? `${latest.battery.toFixed(2)} V` : 'not measured';
    $('imu').textContent = latest.flags & 1 ? 'OK' : 'Not responding';
    $('mic').textContent = latest.flags & 2 ? 'OK' : 'Not responding';
    const [ax, ay, az] = latest.motion[1];
    $('movement').value = Math.abs(Math.hypot(ax, ay, az) - 9.81);
    $('loudness').value = Math.log10(latest.rms + 1);
  }
  showContext();
  if (model?.uses_camera && !demoTimer && device && !cameraOn()) {
    showNotice('This model was trained with the camera. Start the camera, or its guesses will be worse.');
  }

  const listening = device?.gatt?.connected || demoTimer;
  if (listening && !lost && Date.now() - lastPacketAt > LOST_MS) {
    lost = true;
    setStatus('Out of range', 'lost');
    quietBubble(`I can't hear ${DOG}'s collar.`, 'It is switched off, flat, or more than about 10 m away.');
    say("I can't hear the collar.");
  }
}

function startSession(label) {
  predictor?.reset();
  lastSeq = null;
  lost = false;
  lastPacketAt = Date.now();
  spoken = { mood: null, at: 0 };
  setStatus(label, 'on');
  quietBubble(`Listening to ${DOG}…`, 'The first reading takes about 8 seconds.');
  navigator.wakeLock?.request('screen').then((lock) => { wakeLock = lock; }).catch(() => {});
}

function endSession() {
  wakeLock?.release().catch(() => {});
  wakeLock = null;
  latest = null;
  setRecordable(false);
  setStatus('Not connected');
  quietBubble(`Connect ${DOG}'s collar to hear from him.`);
  $('connect').textContent = 'Connect collar';
  $('demo').textContent = 'Try a demo';
}

// ---------------------------------------------------------------- Bluetooth

async function subscribe() {
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(SERVICE_UUID);
  const characteristic = await service.getCharacteristic(SENSOR_CHAR_UUID);
  characteristic.addEventListener('characteristicvaluechanged', (event) => {
    const view = event.target.value;
    if (view.byteLength === PACKET_SIZE) onPacket(decodePacket(view));
  });
  await characteristic.startNotifications();
}

async function reconnect() {
  while (device && !device.gatt.connected) {
    try { await subscribe(); } catch { await new Promise((r) => setTimeout(r, RETRY_MS)); }
  }
}

async function connect() {
  if (device) {   // the button reads "Disconnect"
    const old = device;
    device = null;
    old.gatt.disconnect();
    endSession();
    return;
  }
  if (!navigator.bluetooth) {
    showNotice('This browser cannot use Bluetooth. Open TinyTalk in Chrome or Edge on Android or a computer, or try the demo.');
    return;
  }
  stopDemo();
  try {
    device = await navigator.bluetooth.requestDevice({
      filters: [{ name: DEVICE_NAME }, { services: [SERVICE_UUID] }],
      optionalServices: [SERVICE_UUID],
    });
    device.addEventListener('gattserverdisconnected', reconnect);
    setStatus('Connecting…');
    await subscribe();
    startSession('Connected');
    setRecordable(true);
    $('connect').textContent = 'Disconnect';
  } catch (error) {
    device = null;
    if (error.name !== 'NotFoundError') showNotice(`Could not connect: ${error.message}`);
    endSession();
  }
}

// ---------------------------------------------------------------- Demo
// A simulated collar, so the app can be tried without one. It walks through a
// few made-up scenes; nothing here is a reading of a real dog.

const SCENES = [
  { move: 6, stride: 4, turn: 150, vocal: 0.15, burst: 5, pitch: 700, fed: 120, potty: 60, away: false },   // playing
  { move: 0.05, stride: 0.5, turn: 1, vocal: 0, burst: 1, pitch: 0, fed: 120, potty: 60, away: false },         // asleep
  { move: 0.2, stride: 0.8, turn: 10, vocal: 0.25, burst: 4, pitch: 800, fed: 150, potty: 90, away: false },    // barking at a sound
  { move: 1, stride: 1.5, turn: 30, vocal: 0.1, burst: 15, pitch: 1200, fed: 400, potty: 100, away: false },    // pacing, long after his meal
];
const SCENE_SECONDS = 30;
const BAND_TOP_HZ = [156, 219, 312, 437, 625, 875, 1250, 1781, 2531, 3594, 5094, 8000];
let demoSeq = 0;
let demoVocalLeft = 0;

const demoScene = () => SCENES[Math.floor(demoSeq / (SCENE_SECONDS * 25)) % SCENES.length];
const noise = (scale) => (Math.random() + Math.random() + Math.random() - 1.5) * 2 * scale;

function demoContext() {
  const scene = demoScene();
  return { hour: 18, minsSinceFed: scene.fed, minsSincePotty: scene.potty, ownerAway: scene.away };
}

function demoPacket() {
  const scene = demoScene();
  const motion = [0, 1].map((i) => {
    const t = (demoSeq * 2 + i) / 50;
    const stride = Math.sin(2 * Math.PI * scene.stride * t);
    const spread = 0.03 + 0.2 * scene.move;
    return [
      scene.move * stride * 0.8 + noise(spread), scene.move * stride * 0.5 + noise(spread),
      9.81 + scene.move * stride * 0.6 + noise(spread),
      scene.turn * stride * 0.7 + 2 * Math.sin(2 * Math.PI * 0.45 * t) + noise(0.5 + 0.1 * scene.turn),
      scene.turn * stride * 0.4 + noise(0.5 + 0.1 * scene.turn),
      scene.turn * stride * 0.9 + noise(0.5 + 0.1 * scene.turn),
    ];
  });
  if (demoVocalLeft === 0 && Math.random() < scene.vocal / scene.burst) demoVocalLeft = scene.burst;
  const vocal = demoVocalLeft > 0;
  if (vocal) demoVocalLeft--;
  const pitch = vocal ? scene.pitch * (0.9 + 0.2 * Math.random()) : 100 + 200 * Math.random();
  const bands = Array.from({ length: NUM_BANDS }, () => Math.round(18 + 4 * Math.random()));
  if (vocal) {
    const band = BAND_TOP_HZ.findIndex((top) => pitch <= top);
    [[0, 45], [1, 25], [-1, 20]].forEach(([offset, gain]) => {
      bands[Math.max(0, Math.min(NUM_BANDS - 1, band + offset))] += gain;
    });
  }
  const packet = {
    seq: demoSeq & 0xffff,
    motion,
    rms: Math.round(45 + 20 * Math.random() + (vocal ? 2000 + 6000 * Math.random() : 0)),
    domHz: Math.round(pitch / 31.25) * 31.25,
    zcr: Math.min(255, Math.round(pitch * 0.032)),
    flags: 3,
    bands,
    battery: 3.9,
  };
  demoSeq++;
  return packet;
}

function stopDemo() {
  if (!demoTimer) return;
  clearInterval(demoTimer);
  demoTimer = null;
  showNotice(model?.synthetic ? STARTER_NOTICE : '');
  endSession();
}

function toggleDemo() {
  if (demoTimer) { stopDemo(); return; }
  if (device) connect();   // disconnect the real collar first
  demoSeq = 0;
  startSession('Demo');
  $('demo').textContent = 'Stop the demo';
  showNotice('Demo: a simulated collar is playing made-up scenes. None of this is a reading of a real dog.');
  // Catch up by the clock, because browsers slow timers down
  const started = Date.now();
  demoTimer = setInterval(() => {
    const due = Math.floor((Date.now() - started) / 40);
    for (let i = 0; i < 50 && demoSeq < due; i++) onPacket(demoPacket());
  }, 40);
}

// ---------------------------------------------------------------- Page

const STARTER_NOTICE = `Starter model: it was trained on simulated data, so the phrases are not yet real readings of ${DOG}. Record and train on his own data to change that.`;

function showNotice(text) {
  $('notice').textContent = text;
  $('notice').hidden = !text;
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach((tab) => { tab.hidden = tab.id !== `tab-${name}`; });
  document.querySelectorAll('nav button').forEach((button) => {
    if (button.dataset.tab === name) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
}

document.querySelectorAll('nav button').forEach((button) => {
  button.addEventListener('click', () => showTab(button.dataset.tab));
});
$('status').addEventListener('click', () => showTab('collar'));
$('connect').addEventListener('click', connect);
$('demo').addEventListener('click', toggleDemo);
document.querySelectorAll('[data-event]').forEach((button) => {
  button.addEventListener('click', () => {
    if (button.dataset.event === 'fed') context.lastFed = Date.now();
    else if (button.dataset.event === 'went') context.lastPotty = Date.now();
    else context.ownerAway = !context.ownerAway;
    save('context', context);
    showContext();
  });
});

quietBubble(`Connect ${DOG}'s collar to hear from him.`);
showContext();
setInterval(refresh, 1000);

fetch('model.json').then((response) => response.json()).then((loaded) => {
  model = loaded;
  predictor = new MoodPredictor(model);
  setMoods(Object.keys(model.phrases));
  $('model-info').textContent = model.synthetic
    ? `Starter (simulated data), ${model.classes.length} moods`
    : `${model.classes.length} moods, ${Math.round(model.held_out_accuracy * 100)}% on held-out sessions` +
      (model.uses_camera ? '; trained with the camera' : '');
  if (model.synthetic && !demoTimer) showNotice(STARTER_NOTICE);
}).catch(() => {
  $('model-info').textContent = 'Could not load';
  showNotice('The mood model could not be loaded. Check your connection and reload.');
});

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
