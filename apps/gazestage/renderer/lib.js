// Pure helpers shared by the app and the unit tests. No DOM, no browser APIs.

// ---------- smoothing ----------
// One Euro filter: low jitter while the pointer is still, low lag while it moves.
// smoothing: 0 (raw) .. 10 (very smooth).
export class OneEuro {
  constructor(smoothing = 5) { this.reset(); this.setSmoothing(smoothing); }
  reset() { this.x = null; this.dx = 0; this.t = 0; }
  setSmoothing(s) { this.minCutoff = 3.0 / (1 + s); this.beta = 0.02 / (1 + s * 0.5); }
  static alpha(cutoff, dt) { const tau = 1 / (2 * Math.PI * cutoff); return 1 / (1 + tau / dt); }
  filter(v, tMs) {
    if (this.x == null) { this.x = v; this.t = tMs; return v; }
    const dt = Math.max((tMs - this.t) / 1000, 1e-3); this.t = tMs;
    const dx = (v - this.x) / dt;
    this.dx += OneEuro.alpha(1, dt) * (dx - this.dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x += OneEuro.alpha(cutoff, dt) * (v - this.x);
    return this.x;
  }
}

// ---------- calibration ----------
// Ridge-regularised least squares: weights w such that X·w ≈ y. Returns null when unsolvable.
export function leastSquares(X, y, ridge = 1e-6) {
  if (!X.length || X.length !== y.length) return null;
  const n = X[0].length, A = Array.from({ length: n }, () => new Array(n + 1).fill(0));
  for (let k = 0; k < X.length; k++)
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) A[i][j] += X[k][i] * X[k][j];
      A[i][n] += X[k][i] * y[k];
    }
  for (let i = 0; i < n; i++) A[i][i] += ridge;
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]];
    if (Math.abs(A[c][c]) < 1e-12) return null;
    for (let r = 0; r < n; r++) if (r !== c) {
      const f = A[r][c] / A[c][c];
      for (let j = c; j <= n; j++) A[r][j] -= f * A[c][j];
    }
  }
  return A.map((row, i) => row[n] / row[i]);
}
export const dot = (w, f) => w.reduce((s, wi, i) => s + wi * f[i], 0);

// Fit screen x and y (0..1) from feature vectors. Also reports the mean error as a fraction
// of the screen diagonal so the app can say how good the calibration is.
export function fitCalibration(samples) {
  const X = samples.map(s => s.f);
  const wx = leastSquares(X, samples.map(s => s.x));
  const wy = leastSquares(X, samples.map(s => s.y));
  if (!wx || !wy) return null;
  let err = 0;
  for (const s of samples) err += Math.hypot(dot(wx, s.f) - s.x, dot(wy, s.f) - s.y);
  return { wx, wy, error: err / samples.length / Math.SQRT2 };
}
export function calibrationGrade(error) {
  if (error < 0.04) return 'great';
  if (error < 0.07) return 'good';
  if (error < 0.11) return 'fair';
  return 'poor';
}

// ---------- head pointer without calibration ----------
// range: degrees of head turn that sweep the full screen width (smaller = less movement needed).
export function headToScreen(yaw, pitch, neutral, rangeDeg, W, H) {
  const rad = (rangeDeg * Math.PI) / 180;
  const x = 0.5 - (yaw - neutral.yaw) / rad;
  // Looking up and down is harder than turning, so vertical needs only 70% of the range.
  const y = 0.5 - (pitch - neutral.pitch) / (rad * 0.7);
  return [x * W, y * H];
}

// ---------- music ----------
export const NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];
export const SCALES = {
  Major: [0, 2, 4, 5, 7, 9, 11],
  Minor: [0, 2, 3, 5, 7, 8, 10],
  Pentatonic: [0, 2, 4, 7, 9],
  'Minor pentatonic': [0, 3, 5, 7, 10],
  Blues: [0, 3, 5, 6, 7, 10],
  Dorian: [0, 2, 3, 5, 7, 9, 10],
  Chromatic: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
};
export const noteName = (n) => NOTE_NAMES[((n % 12) + 12) % 12] + (Math.floor(n / 12) - 1);

// Midi note of scale degree i (0-based, may exceed one octave).
function degree(scale, rootMidi, i) {
  const len = scale.length;
  return rootMidi + scale[((i % len) + len) % len] + 12 * Math.floor(i / len);
}

// Pads in ascending order. Each pad is { notes: [midi...], label, sub, isRoot }.
// chords: stack scale thirds (degree, +2, +4) so every pad is a chord that fits the key.
export function buildPads({ key = 0, octave = 4, scale = 'Major', count = 8, chords = false }) {
  const steps = SCALES[scale] || SCALES.Major;
  const root = 12 * (octave + 1) + key;
  const pads = [];
  for (let i = 0; i < count; i++) {
    const base = degree(steps, root, i);
    const notes = chords && steps.length >= 5 ? [base, degree(steps, root, i + 2), degree(steps, root, i + 4)] : [base];
    pads.push({
      notes,
      label: chords ? chordName(notes) : noteName(base),
      sub: chords ? noteName(base) : (i % steps.length === 0 ? 'root' : ''),
      isRoot: i % steps.length === 0,
    });
  }
  return pads;
}
export function chordName([a, b, c]) {
  const n = NOTE_NAMES[((a % 12) + 12) % 12];
  const third = b - a, fifth = c - a;
  if (third === 4 && fifth === 7) return n;
  if (third === 3 && fifth === 7) return n + 'm';
  if (third === 3 && fifth === 6) return n + '°';
  if (third === 4 && fifth === 8) return n + '+';
  return n + ' chord';
}

// ---------- HUI (Pro Tools control surface protocol over MIDI) ----------
// Surface → host button press: CC 0x0F = zone, then CC 0x2F = port | 0x40 (down) or port (up).
export const HUI = {
  TRANSPORT_ZONE: 0x0e,
  PORT: { rewind: 1, fastForward: 2, stop: 3, play: 4, record: 5 },
  PING: [0x90, 0x00, 0x00],
  PING_REPLY: [0x90, 0x00, 0x7f],
};
export function huiSwitch(zone, port, down) {
  return [0xb0, 0x0f, zone, 0xb0, 0x2f, (down ? 0x40 : 0) | port];
}

// Host → surface parser. Pro Tools pings (note-on 0, velocity 0) about once a second and
// lights button LEDs with CC 0x0C = zone, then CC 0x2C = port | 0x40 (on) or port (off),
// often with running status. Feed raw bytes; get { type: 'ping' } and { type: 'led', zone, port, on }.
export class HuiParser {
  constructor() { this.status = 0; this.data = []; this.zone = null; }
  feed(bytes) {
    const out = [];
    for (const b of bytes) {
      if (b >= 0xf8) continue;                     // realtime bytes never affect running status
      if (b & 0x80) { this.status = b; this.data = []; continue; }
      if (!this.status) continue;
      this.data.push(b);
      const type = this.status & 0xf0;
      const need = type === 0xc0 || type === 0xd0 ? 1 : type >= 0xf0 ? Infinity : 2;
      if (this.data.length < need) continue;
      const [d1, d2] = this.data; this.data = [];
      if (this.status === 0x90 && d1 === 0 && d2 === 0) out.push({ type: 'ping' });
      else if (type === 0xb0 && d1 === 0x0c) this.zone = d2;
      else if (type === 0xb0 && d1 === 0x2c && this.zone != null)
        out.push({ type: 'led', zone: this.zone, port: d2 & 0x0f, on: (d2 & 0x40) !== 0 });
    }
    return out;
  }
}

// ---------- sound switch ----------
// Detects short loud sounds (pop, click, "ta") in a stream of RMS levels.
// sensitivity: 1 (needs a loud sound) .. 20 (very light).
export class OnsetDetector {
  constructor() { this.floor = 0.01; this.armed = true; this.last = -1e9; }
  threshold(sensitivity) { return Math.max(this.floor * 3, 0.32 / sensitivity); }
  push(rms, tMs, sensitivity) {
    this.floor = rms < this.floor ? rms : this.floor * 0.999 + rms * 0.001;
    const th = this.threshold(sensitivity);
    let hit = false;
    if (this.armed && rms > th && tMs - this.last > 150) { this.armed = false; this.last = tMs; hit = true; }
    if (!this.armed && rms < th * 0.5) this.armed = true;
    return { hit, level: Math.min(rms / (th * 1.5), 1) };
  }
}
