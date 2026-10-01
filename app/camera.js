// Cage camera for TinyTalk: finds the dog's outline in each frame of a fixed
// view by comparing it with a picture of the empty cage.
//
// It follows the same steps as DogFinder in ml/camera.py, but the two are not
// interchangeable: the phone scales and measures the picture differently from
// OpenCV, so a model must be trained on recordings made with the same one.
// No DOM here, so check_camera.mjs can run it under Node.

export const PROCESS_WIDTH = 320;   // frames are shrunk to this width before analysis
const MIN_DOG_AREA = 0.002;         // smaller shapes are treated as noise
const DOG_THRESHOLD = 20;           // brightness difference from the empty cage that counts as "dog"
const MOTION_THRESHOLD = 15;        // brightness change between frames that counts as movement
const LIGHTING_CHANGE = 0.6;        // if this much of the picture differs, the lights changed
const DOG_MARGIN = 8;               // pixels around him where the empty-cage picture adapts slowly

// 5 x 5 ellipse, as offsets from the centre
const ELLIPSE = [];
for (let dy = -2; dy <= 2; dy++) {
  for (let dx = -2; dx <= 2; dx++) if (Math.abs(dy) < 2 || dx === 0) ELLIPSE.push([dx, dy]);
}

/** Camera pixels (RGBA) to a blurred grey picture, one number per pixel. */
export function prepare(rgba, width, height) {
  const grey = new Float32Array(width * height);
  for (let i = 0; i < grey.length; i++) {
    grey[i] = 0.299 * rgba[i * 4] + 0.587 * rgba[i * 4 + 1] + 0.114 * rgba[i * 4 + 2];
  }
  return blur(grey, width, height);
}

/** 5 x 5 Gaussian blur, done as one pass across and one pass down. */
export function blur(source, width, height) {
  const taps = [1 / 16, 4 / 16, 6 / 16, 4 / 16, 1 / 16];
  const across = new Float32Array(source.length);
  const out = new Float32Array(source.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let k = -2; k <= 2; k++) sum += taps[k + 2] * source[y * width + Math.min(width - 1, Math.max(0, x + k))];
      across[y * width + x] = sum;
    }
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let k = -2; k <= 2; k++) sum += taps[k + 2] * across[Math.min(height - 1, Math.max(0, y + k)) * width + x];
      out[y * width + x] = sum;
    }
  }
  return out;
}

/** Grow (grow = true) or shrink the marked area by the ellipse. */
function morph(mask, width, height, grow) {
  const out = new Uint8Array(mask.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let hit = grow ? 0 : 1;
      for (const [dx, dy] of ELLIPSE) {
        const nx = x + dx, ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
        if (grow ? mask[ny * width + nx] : !mask[ny * width + nx]) { hit = grow ? 1 : 0; break; }
      }
      out[y * width + x] = hit;
    }
  }
  return out;
}

/** Grow the marked area by a square of the given radius. */
function widen(mask, width, height, radius) {
  const across = new Uint8Array(mask.length);
  const out = new Uint8Array(mask.length);
  for (let y = 0; y < height; y++) {
    let last = -Infinity;
    for (let x = 0; x < width; x++) { if (mask[y * width + x]) last = x; if (x - last <= radius) across[y * width + x] = 1; }
    last = Infinity;
    for (let x = width - 1; x >= 0; x--) { if (mask[y * width + x]) last = x; if (last - x <= radius) across[y * width + x] = 1; }
  }
  for (let x = 0; x < width; x++) {
    let last = -Infinity;
    for (let y = 0; y < height; y++) { if (across[y * width + x]) last = y; if (y - last <= radius) out[y * width + x] = 1; }
    last = Infinity;
    for (let y = height - 1; y >= 0; y--) { if (across[y * width + x]) last = y; if (last - y <= radius) out[y * width + x] = 1; }
  }
  return out;
}

/** The largest connected shape in the mask: its pixel count and bounding box. */
function largestShape(mask, width, height) {
  const seen = new Uint8Array(mask.length);
  const stack = new Int32Array(mask.length);
  let best = null;
  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || seen[start]) continue;
    let top = 0, count = 0, x0 = width, y0 = height, x1 = 0, y1 = 0;
    stack[top++] = start;
    seen[start] = 1;
    while (top) {
      const at = stack[--top];
      const x = at % width, y = (at - x) / width;
      count++;
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const next = ny * width + nx;
          if (mask[next] && !seen[next]) { seen[next] = 1; stack[top++] = next; }
        }
      }
    }
    if (!best || count > best.count) best = { count, x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
  }
  return best;
}

function median(values) {
  const sorted = Float32Array.from(values).sort();
  return sorted[sorted.length >> 1];
}

const round = (value, places) => Math.round(value * 10 ** places) / 10 ** places;

export class DogFinder {
  /** emptyCage: a prepared picture (from prepare()) of the cage with no dog in it. */
  constructor(width, height, emptyCage) {
    this.width = width;
    this.height = height;
    this.emptyCage = Float32Array.from(emptyCage);
    this.previous = null;
    this.last = null;
  }

  /**
   * Analyse one prepared frame. Returns { x, y, w, h, area, motion } as
   * fractions of the picture, or null if he has not been seen yet.
   */
  update(frame) {
    const { width, height } = this;
    const size = width * height;

    let moved = 0;
    if (this.previous) {
      for (let i = 0; i < size; i++) if (Math.abs(frame[i] - this.previous[i]) > MOTION_THRESHOLD) moved++;
    }
    const motion = this.previous ? moved / size : 0;
    this.previous = frame;

    // A light switched on or off brightens the whole picture at once:
    // shift the empty-cage picture by the same amount before comparing
    const sample = [];
    for (let i = 0; i < size; i += 7) sample.push(frame[i] - this.emptyCage[i]);
    const shift = median(sample);

    let mask = new Uint8Array(size);
    for (let i = 0; i < size; i++) {
      this.emptyCage[i] += shift;
      if (Math.abs(frame[i] - this.emptyCage[i]) > DOG_THRESHOLD) mask[i] = 1;
    }
    mask = morph(morph(mask, width, height, false), width, height, true);    // drop specks
    mask = morph(morph(mask, width, height, true), width, height, false);    // fill small holes

    let marked = 0;
    for (let i = 0; i < size; i++) marked += mask[i];
    if (marked / size > LIGHTING_CHANGE) {
      // The picture no longer resembles the empty cage (night vision switched
      // on, or the camera moved). Report nothing new rather than guess.
      mask = new Uint8Array(size);
    } else {
      // Follow slow lighting drift quickly where the dog is not, and very
      // slowly where he is, so a moved blanket stops counting as "dog" after
      // several minutes. The price: a dog asleep that long fades too, and
      // the tracker then holds his last position.
      const dog = widen(mask, width, height, DOG_MARGIN);
      for (let i = 0; i < size; i++) {
        const rate = dog[i] ? 0.0002 : 0.01;
        this.emptyCage[i] += rate * (frame[i] - this.emptyCage[i]);
      }
    }

    const shape = largestShape(mask, width, height);
    if (shape && shape.count >= MIN_DOG_AREA * size) {
      this.last = {
        x: round((shape.x + shape.w / 2) / width, 3),
        y: round((shape.y + shape.h / 2) / height, 3),
        w: round(shape.w / width, 3),
        h: round(shape.h / height, 3),
        area: round(shape.count / size, 4),
        motion: round(motion, 4),
      };
    } else if (this.last) {
      // Lost sight of him. He is still in the cage, so keep his last position.
      this.last = { ...this.last, motion: round(motion, 4) };
    }
    return this.last;
  }
}
