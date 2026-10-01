// The Camera tab: runs the phone's camera, keeps the empty-cage picture, and
// offers the tracker's latest result to the rest of the app.

import { DogFinder, PROCESS_WIDTH, prepare } from './camera.js';

const FRAME_MS = 100;        // about 10 pictures a second, as ml/camera.py does
const STALE_MS = 2000;       // older than this and the result is not used
const CAGE_KEY = 'cage';

const $ = (id) => document.getElementById(id);
const work = document.createElement('canvas');

let stream = null;
let timer = null;
let finder = null;
let frame = null;            // the latest prepared picture
let size = null;             // { w, h } of the pictures being analysed
let result = null;
let resultAt = 0;

/** The tracker's latest result, or null when the camera is off or has not seen him. */
export function currentCam() {
  return stream && Date.now() - resultAt < STALE_MS ? result : null;
}

export const cameraOn = () => stream !== null;

function loadCage() {
  try {
    const saved = JSON.parse(localStorage.getItem(CAGE_KEY));
    const bytes = Uint8Array.from(atob(saved.data), (c) => c.charCodeAt(0));
    return { w: saved.w, h: saved.h, picture: Float32Array.from(bytes) };
  } catch { return null; }
}

function saveCage() {
  const bytes = Uint8Array.from(frame, (v) => Math.round(v));
  let text = '';
  for (let i = 0; i < bytes.length; i += 8192) text += String.fromCharCode(...bytes.subarray(i, i + 8192));
  try {
    localStorage.setItem(CAGE_KEY, JSON.stringify({ w: size.w, h: size.h, data: btoa(text) }));
  } catch { /* private window: the picture lasts until the page closes */ }
  finder = new DogFinder(size.w, size.h, frame);
  result = null;
}

function tick() {
  const video = $('video');
  if (!video.videoWidth) return;
  const w = PROCESS_WIDTH;
  const h = Math.round(w * video.videoHeight / video.videoWidth);
  if (!size || size.w !== w || size.h !== h) {
    // First picture, or the phone was turned: the old empty-cage picture no longer fits
    size = { w, h };
    work.width = w;
    work.height = h;
    const cage = loadCage();
    finder = cage && cage.w === w && cage.h === h ? new DogFinder(w, h, cage.picture) : null;
    result = null;
  }
  const pen = work.getContext('2d', { willReadFrequently: true });
  pen.drawImage(video, 0, 0, w, h);
  frame = prepare(pen.getImageData(0, 0, w, h).data, w, h);
  if (finder) result = finder.update(frame);
  resultAt = Date.now();

  const view = $('view');
  view.width = w;
  view.height = h;
  const paint = view.getContext('2d');
  paint.drawImage(work, 0, 0);
  if (result) {
    paint.lineWidth = 2;
    paint.strokeStyle = '#f0914f';
    paint.strokeRect((result.x - result.w / 2) * w, (result.y - result.h / 2) * h, result.w * w, result.h * h);
  }
  $('empty-cage').disabled = false;
  $('camera-state').textContent = !finder
    ? 'No empty-cage picture for this view yet. Take him out of the cage, then take one.'
    : result ? `Sees him. Movement ${(result.motion * 100).toFixed(1)}%.` : 'Watching. He has not been seen yet.';
}

function stop() {
  clearInterval(timer);
  stream?.getTracks().forEach((track) => track.stop());
  stream = timer = size = finder = frame = result = null;
  $('camera-toggle').textContent = 'Start camera';
  $('empty-cage').disabled = true;
  $('camera-state').textContent = 'Camera is off.';
}

async function start() {
  if (!navigator.mediaDevices?.getUserMedia) {
    $('camera-state').textContent = 'This browser cannot use the camera.';
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 640 } }, audio: false,
    });
  } catch (error) {
    stream = null;
    $('camera-state').textContent = `Could not start the camera: ${error.message}`;
    return;
  }
  const video = $('video');
  video.srcObject = stream;
  await video.play().catch(() => {});
  $('camera-toggle').textContent = 'Stop camera';
  $('camera-state').textContent = 'Starting…';
  timer = setInterval(tick, FRAME_MS);
}

$('camera-toggle').addEventListener('click', () => (stream ? stop() : start()));
$('empty-cage').addEventListener('click', () => { if (frame) saveCage(); });
