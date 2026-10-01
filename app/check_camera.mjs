// Checks the camera tracker on made-up pictures: a dark dog-shaped blob on a
// lighter, slightly textured cage floor. This shows the arithmetic works; it
// says nothing about a real camera, cage or dog.
//
//   node app/check_camera.mjs

import { DogFinder, prepare } from './camera.js';

const W = 320, H = 240;
let failed = false;

function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? `  (${detail})` : ''}`);
}

/** A picture of the cage; dog = { x, y, w, h } in pixels, or null for the empty cage. */
function picture(dog, brightness = 0, seed = 1) {
  const rgba = new Uint8ClampedArray(W * H * 4);
  let state = seed;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      state = (state * 1103515245 + 12345) & 0x7fffffff;
      let value = 170 + 10 * Math.sin(x / 9) + (state % 7) + brightness;
      if (dog && ((x - dog.x) / (dog.w / 2)) ** 2 + ((y - dog.y) / (dog.h / 2)) ** 2 <= 1) value = 60 + (state % 9);
      const i = (y * W + x) * 4;
      rgba[i] = rgba[i + 1] = rgba[i + 2] = value;
      rgba[i + 3] = 255;
    }
  }
  return prepare(rgba, W, H);
}

const near = (a, b, tolerance) => Math.abs(a - b) <= tolerance;

// 1. Nothing is reported for an empty cage
let finder = new DogFinder(W, H, picture(null));
let seen = null;
for (let i = 0; i < 5; i++) seen = finder.update(picture(null, 0, 2 + i));
check('empty cage reports nothing', seen === null);

// 2. A dog lying down is found where he is, wider than tall
const lying = { x: 200, y: 150, w: 90, h: 40 };
seen = finder.update(picture(lying, 0, 9));
check('finds him', seen !== null && near(seen.x, lying.x / W, 0.02) && near(seen.y, lying.y / H, 0.02),
  seen && `x ${seen.x} y ${seen.y}`);
check('outline is wide and low', seen && near(seen.w, lying.w / W, 0.03) && near(seen.h, lying.h / H, 0.03) && seen.w > seen.h,
  seen && `w ${seen.w} h ${seen.h}`);
check('area matches', seen && near(seen.area, Math.PI * 45 * 20 / (W * H), 0.005), seen && `area ${seen.area}`);

// 3. He walks across: position follows, and movement is reported
let travelled = 0;
for (let step = 1; step <= 10; step++) {
  const before = seen.x;
  seen = finder.update(picture({ ...lying, x: 200 - step * 12 }, 0, 20 + step));
  travelled += before - seen.x;
}
check('follows him across the cage', near(seen.x, 80 / W, 0.02) && travelled > 0.3, `x ${seen.x}`);
check('reports movement while he walks', seen.motion > 0.01, `motion ${seen.motion}`);

// 4. He stays put for two minutes of frames and is still seen, with no movement
for (let i = 0; i < 1200; i++) seen = finder.update(picture({ ...lying, x: 80 }, 0, 100 + (i % 5)));
check('still sees him after 2 minutes asleep', near(seen.x, 80 / W, 0.02) && seen.area > 0.02, `area ${seen.area}`);
check('no movement while he is still', seen.motion < 0.005, `motion ${seen.motion}`);

// 5. A lamp is switched on: the whole picture brightens, he is still found
seen = finder.update(picture({ ...lying, x: 80 }, 35, 300));
check('survives a lamp switching on', near(seen.x, 80 / W, 0.03) && near(seen.w, lying.w / W, 0.05), `x ${seen.x} w ${seen.w}`);

// 6. A sitting dog is taller than wide
finder = new DogFinder(W, H, picture(null));
seen = finder.update(picture({ x: 160, y: 120, w: 40, h: 70 }, 0, 400));
check('sitting outline is tall', seen && seen.h * H > seen.w * W, seen && `w ${seen.w} h ${seen.h}`);

// 7. The camera now points somewhere else: no guess is made
finder = new DogFinder(W, H, picture(null));
const elsewhere = picture(null).map((_, i) => (i % W) * 255 / W);   // a different scene altogether
check('reports nothing when the picture no longer matches', finder.update(elsewhere) === null);

// 8. Speed
const started = performance.now();
for (let i = 0; i < 20; i++) finder.update(picture(lying, 0, 500 + i));
const perFrame = (performance.now() - started) / 20;
console.log(`about ${perFrame.toFixed(0)} ms per frame here, picture making included`);

console.log(failed ? 'FAILED' : 'OK: the tracker behaves as intended on made-up pictures');
process.exit(failed ? 1 : 0);
