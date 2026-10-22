import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  displayInUse, shownProgress,
  OneEuro, leastSquares, fitCalibration, calibrationGrade, headToScreen,
  buildPads, chordName, noteName, huiSwitch, HuiParser, HUI, OnsetDetector, XY_PROFILES, toCC, xyMessages, XYMotion,
} from '../renderer/lib.js';

test('least squares recovers a linear map', () => {
  const X = [], y = [];
  for (let i = 0; i < 50; i++) { const a = Math.sin(i), b = Math.cos(i * 1.3); X.push([a, b, 1]); y.push(2 * a - 0.5 * b + 0.25); }
  const w = leastSquares(X, y);
  assert.ok(Math.abs(w[0] - 2) < 1e-4 && Math.abs(w[1] + 0.5) < 1e-4 && Math.abs(w[2] - 0.25) < 1e-4);
});

test('calibration fit reports error and grade', () => {
  const samples = [];
  for (const [x, y] of [[.1, .1], [.5, .1], [.9, .1], [.1, .5], [.5, .5], [.9, .5], [.1, .9], [.5, .9], [.9, .9]])
    for (let k = 0; k < 10; k++) samples.push({ f: [(x - 0.5) * 0.4, (y - 0.5) * 0.3, 1], x, y });
  const fit = fitCalibration(samples);
  assert.ok(fit.error < 1e-3);
  assert.equal(calibrationGrade(fit.error), 'great');
  assert.equal(calibrationGrade(0.2), 'poor');
});

test('one euro filter converges and smooths', () => {
  const f = new OneEuro(5);
  let v; for (let t = 0; t < 2000; t += 16) v = f.filter(100, t);
  assert.ok(Math.abs(v - 100) < 1e-6);
  const g = new OneEuro(8); g.filter(0, 0);
  assert.ok(g.filter(100, 16) < 50, 'a sudden jump is damped');
});

test('head pointer centres on the neutral pose and moves the right way', () => {
  const n = { yaw: 0.1, pitch: -0.05 };
  assert.deepEqual(headToScreen(0.1, -0.05, n, 16, 1000, 800), [500, 400]);
  const [x] = headToScreen(0.1 - (8 * Math.PI) / 180, -0.05, n, 16, 1000, 800);
  assert.ok(Math.abs(x - 1000) < 1e-6, 'half the range reaches the screen edge');
});

test('display uses the more accessible of GazeStage\'s own and the shared settings', () => {
  const own = { size: 'normal', contrast: false, reduceMotion: false };
  const mine = { size: 'xlarge', contrast: true, reduceMotion: true };
  const off = { textScale: 1, highContrast: false, reduceMotion: false };
  assert.deepEqual(displayInUse(own, null), off, 'no hub: GazeStage\'s own settings');
  assert.deepEqual(displayInUse(mine, null), { textScale: 24 / 17, highContrast: true, reduceMotion: true });
  assert.deepEqual(displayInUse(own, { textScale: 1.5, highContrast: true, reduceMotion: true, dwellMs: 1200 }),
    { textScale: 1.5, highContrast: true, reduceMotion: true }, 'only text size, contrast and motion');
  assert.deepEqual(displayInUse(mine, { textScale: 1.25, highContrast: false, reduceMotion: false }),
    { textScale: 24 / 17, highContrast: true, reduceMotion: true }, 'the shared settings never take one away');
  assert.equal(displayInUse({ ...own, size: 'large' }, { textScale: 2 }).textScale, 2);
  assert.equal(displayInUse(own, { textScale: 9 }).textScale, 2);
  assert.deepEqual(displayInUse(own, { textScale: 'big', highContrast: 0 }), off);
});

test('reduced motion draws dwell progress in quarter steps', () => {
  assert.deepEqual([0, 0.1, 0.3, 0.6, 0.9, 1, 1.4].map((p) => shownProgress(p, true)), [0, 0.25, 0.5, 0.75, 1, 1, 1]);
  assert.deepEqual([-1, 0.3, 2].map((p) => shownProgress(p, false)), [0, 0.3, 1]);
});

test('pads follow the scale and build chords in key', () => {
  const pads = buildPads({ key: 0, octave: 4, scale: 'Major', count: 8 });
  assert.deepEqual(pads.map(p => p.notes[0]), [60, 62, 64, 65, 67, 69, 71, 72]);
  assert.equal(pads[0].label, 'C4'); assert.ok(pads[0].isRoot && pads[7].isRoot);
  const chords = buildPads({ key: 0, octave: 4, scale: 'Major', count: 7, chords: true });
  assert.deepEqual(chords.map(p => p.label), ['C', 'Dm', 'Em', 'F', 'G', 'Am', 'B°']);
  assert.equal(chordName([57, 60, 64]), 'Am');
  assert.equal(noteName(61), 'C♯4');
  assert.deepEqual(buildPads({ key: 9, octave: 3, scale: 'Minor', count: 1 })[0].notes, [57]);
});

test('HUI switch messages match the protocol', () => {
  assert.deepEqual(huiSwitch(HUI.TRANSPORT_ZONE, HUI.PORT.play, true), [0xb0, 0x0f, 0x0e, 0xb0, 0x2f, 0x44]);
  assert.deepEqual(huiSwitch(HUI.TRANSPORT_ZONE, HUI.PORT.play, false), [0xb0, 0x0f, 0x0e, 0xb0, 0x2f, 0x04]);
});

test('HUI parser handles pings, LEDs and running status', () => {
  const p = new HuiParser();
  assert.deepEqual(p.feed([0x90, 0x00, 0x00]), [{ type: 'ping' }]);
  assert.deepEqual(p.feed([0xb0, 0x0c, 0x0e, 0x2c, 0x44]), [{ type: 'led', zone: 14, port: 4, on: true }]);
  assert.deepEqual(p.feed([0x2c, 0x04, 0xf8]), [{ type: 'led', zone: 14, port: 4, on: false }]);
  assert.deepEqual(p.feed([0xb0, 0x0c]), []);
  assert.deepEqual(p.feed([0x0e, 0xb0, 0x2c, 0x45]), [{ type: 'led', zone: 14, port: 5, on: true }]);
});

test('onset detector fires once per sound and re-arms after quiet', () => {
  const d = new OnsetDetector(); let t = 0, hits = 0;
  const run = (rms, n) => { for (let i = 0; i < n; i++) hits += d.push(rms, (t += 16), 10).hit ? 1 : 0; };
  run(0.005, 100); run(0.3, 10); run(0.005, 30); run(0.3, 10);
  assert.equal(hits, 2);
});

test('XY pad: CC messages only for what changed, on the right channel', () => {
  let r = xyMessages(1, 16, 17, 0, 1);
  assert.deepEqual(r.bytes, [0xb0, 16, 0, 0xb0, 17, 127]);
  r = xyMessages(1, 16, 17, 0.5, 1, r.sent);
  assert.deepEqual(r.bytes, [0xb0, 16, 64]);
  assert.deepEqual(xyMessages(1, 16, 17, 0.5, 1, r.sent).bytes, []);
  assert.deepEqual(xyMessages(16, 1, 2, -3, 9).bytes, [0xbf, 1, 0, 0xbf, 2, 127]);
  assert.equal(toCC(0.25), 32);
  assert.equal(XY_PROFILES.helix.x, 1);
});

test('XY pad: glides ease to the target and chase follows a moving point', () => {
  const m = new XYMotion(0, 0);
  m.glideTo(1, 0.5, 1000, 0);
  m.step(0);
  const [mx] = m.step(500);
  assert.ok(Math.abs(mx - 0.5) < 1e-9, 'halfway in time is halfway in value');
  assert.ok(m.step(250)[0] < 0.25, 'eases in');
  assert.deepEqual(m.step(1000), [1, 0.5]); assert.equal(m.moving, false);
  m.glideTo(0.2, 0.2, 0, 1000); assert.deepEqual([m.x, m.y], [0.2, 0.2]);
  m.chaseTo(0.8, 0.8, 100);
  let t = 1000; m.step(t);
  for (let i = 0; i < 6; i++) m.step(t += 16);
  assert.ok(m.x > 0.3 && m.x < 0.8, 'chase moves part of the way quickly');
  for (let i = 0; i < 200; i++) m.step(t += 16);
  assert.ok(Math.abs(m.x - 0.8) < 1e-3);
  assert.equal(m.moving, false, 'a chase that has arrived is over, so the window can rest');
});
