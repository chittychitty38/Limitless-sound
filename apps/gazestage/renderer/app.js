// GazeStage app: pointer, targeting, selection, pages, guided setup and settings.
import {
  OneEuro, fitCalibration, calibrationGrade, dot, headToScreen, buildPads, SCALES, NOTE_NAMES, HUI, OnsetDetector,
} from './lib.js';
import { Tracker } from './tracker.js';
import { Synth, SYNTH_PRESETS } from './synth.js';
import { MidiRouter } from './midi.js';

const $ = (id) => document.getElementById(id);
const bridge = window.gazestage || null;
if (bridge?.platform === 'darwin') document.body.classList.add('mac');

// ---------- settings ----------
const DEFAULTS = {
  mode: 'head', range: '16', smooth: 5, camera: '', preview: true,
  select: 'dwell', dwell: 900, padDwell: 250, blink: 450, mic: 10, tick: true,
  builtIn: true, preset: 'keys', volume: 0.8, key: 0, scale: 'Major', pads: 8, velocity: 100, octave: 4, chords: false, hold: false,
  theme: 'dark', contrast: false, size: 'normal', spacing: 'normal', onTop: false,
  onboarded: false, cal: {},
};
const KEY = 'gazestage.settings.v3';
const S = (() => { try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return { ...DEFAULTS }; } })();
function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch {} }
const store = { get: (k, d) => (k in S ? S[k] : d), set: (k, v) => { S[k] = v; save(); } };

// ---------- state ----------
const state = {
  page: 'transport', paused: false, cameraOn: false, cameraState: 'off',
  px: innerWidth / 2, py: innerHeight / 2, visible: false,
  sample: null, faceSince: 0, lostSince: 0, autoCentre: [],
  neutral: { yaw: 0, pitch: 0 }, offset: { x: 0, y: 0 },
  current: null, candidate: null, candidateSince: 0, enteredAt: 0, fired: false,
  heldHui: null, blinkSince: 0, calibrating: false, settingsOpen: false,
  onboardStep: null, practiceDone: new Set(),
};
const filterX = new OneEuro(S.smooth), filterY = new OneEuro(S.smooth);
const tracker = new Tracker($('cam'));
const synth = new Synth(); synth.setPreset(S.preset);
const midi = new MidiRouter(store);
const onset = new OnsetDetector();
window.__gs = { state, S, synth, midi };   // for the smoke test

// ---------- display ----------
function applyDisplay() {
  const r = document.documentElement;
  r.dataset.theme = S.theme; r.dataset.contrast = S.contrast ? 'high' : 'normal';
  r.dataset.size = S.size; r.dataset.spacing = S.spacing;
  $('preview').classList.toggle('hidden', !S.preview || !state.cameraOn);
  bridge?.setAlwaysOnTop(S.onTop);
}

let toastTimer = 0;
function toast(msg, ms = 2600) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), ms);
}

function chip(id, level, html) {
  const c = $(id); c.querySelector('.dot').className = 'dot ' + (level || '');
  c.querySelector('span:last-child').innerHTML = html;
}
const SELECT_NAMES = { dwell: 'Dwell', switch: 'Switch', sound: 'Sound', blink: 'Blink' };
function refreshChips() {
  const cam = {
    off: [S.mode === 'mouse' ? 'ok' : '', S.mode === 'mouse' ? 'Pointer <b>mouse</b>' : 'Camera <b>off</b>'],
    loading: ['warn', 'Camera <b>starting…</b>'],
    tracking: ['ok', 'Camera <b>tracking</b>'],
    noface: ['warn', 'Camera <b>no face</b>'],
    error: ['bad', 'Camera <b>unavailable</b>'],
  }[state.cameraState];
  chip('chipCamera', cam[0], cam[1]);
  chip('chipSelect', 'ok', `Select <b>${SELECT_NAMES[S.select]}</b>`);
  if (midi.mode === 'native') chip('chipMidi', 'ok', 'MIDI <b>GazeStage ports</b>');
  else if (midi.mode === 'web') chip('chipMidi', midi.canSendHui || midi.notesTarget ? 'ok' : 'warn', `MIDI <b>${midi.canSendHui || midi.notesTarget ? 'connected' : 'choose ports'}</b>`);
  else chip('chipMidi', 'bad', 'MIDI <b>off</b>');
  chip('chipPT', midi.proToolsConnected ? 'ok' : '', `Pro Tools <b>${midi.proToolsConnected ? 'linked' : 'not linked'}</b>`);
  const hint = $('transportHint');
  if (midi.proToolsConnected) hint.textContent = 'Connected to Pro Tools.';
  else if (midi.mode === 'native') hint.innerHTML = 'Not linked yet. In Pro Tools, add a HUI controller using <b>GazeStage HUI</b>. <button class="linkish" data-cmd="settings">How to connect</button>';
  else hint.innerHTML = 'Not linked yet. <button class="linkish" data-cmd="settings">Choose the Pro Tools ports in Settings</button>';
}
setInterval(refreshChips, 1000);

// ---------- camera ----------
async function startCamera() {
  if (state.cameraOn || state.cameraState === 'loading') return true;
  state.cameraState = 'loading'; refreshChips();
  try {
    if (bridge) {
      const ok = await bridge.media.ask('camera');
      if (!ok) throw Object.assign(new Error('Camera access is turned off for GazeStage'), { name: 'NotAllowedError' });
    }
    await tracker.load();
    await tracker.open(S.camera);
    tracker.onSample = onSample;
    tracker.start();
    state.cameraOn = true; state.cameraState = 'tracking'; state.autoCentre = [];
    applyDisplay(); fillCameras();
    for (const v of document.querySelectorAll('video[data-mirror]')) v.srcObject = tracker.stream;
    return true;
  } catch (e) {
    console.error(e);
    state.cameraState = 'error'; refreshChips();
    state.cameraError = e.name === 'NotAllowedError' || /denied|turned off/i.test(e.message) ? 'denied' : (e.message || String(e));
    return false;
  } finally { refreshChips(); }
}
async function fillCameras() {
  const sel = $('sCamera'); const cams = await Tracker.cameras();
  sel.length = 1;
  cams.forEach((c, i) => sel.add(new Option(c.label || 'Camera ' + (i + 1), c.deviceId)));
  sel.value = cams.some(c => c.deviceId === S.camera) ? S.camera : '';
}

// One camera frame.
function onSample(s) {
  state.sample = s;
  const now = performance.now();
  if (!s.face) {
    if (!state.lostSince) state.lostSince = now;
    state.faceSince = 0;
    if (state.cameraState === 'tracking' && now - state.lostSince > 400) { state.cameraState = 'noface'; refreshChips(); }
    updateOnboardChecks(s);
    return;
  }
  if (!state.faceSince) state.faceSince = now;
  state.lostSince = 0;
  if (state.cameraState !== 'tracking') { state.cameraState = 'tracking'; refreshChips(); }
  // Centre the head pointer automatically on the first second of tracking.
  // (The first few frames are skipped: the tracker is still settling.)
  if (state.autoCentre && s.blink < 0.35) {
    state.autoCentre.push(s);
    if (state.autoCentre.length === 25) { setNeutral(state.autoCentre.slice(5)); state.autoCentre = null; }
  }
  updateOnboardChecks(s);
  if (S.mode === 'mouse' || state.calibrating) return;
  // Freeze the pointer while the eyes are closing so a blink never moves it.
  if (s.blink > 0.35) return;
  const [x, y] = mapToScreen(s);
  state.raw = [x, y];
  state.px = filterX.filter(clamp(x + state.offset.x, 0, innerWidth - 1), now);
  state.py = filterY.filter(clamp(y + state.offset.y, 0, innerHeight - 1), now);
}
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const features = (s, mode = S.mode) => (mode === 'eyes' ? [s.ix, s.iy, s.yaw, s.pitch, 1] : [s.yaw, s.pitch, 1]);
function mapToScreen(s) {
  const cal = S.cal[S.mode];
  if (cal && S.mode !== 'mouse') { const f = features(s); return [dot(cal.wx, f) * innerWidth, dot(cal.wy, f) * innerHeight]; }
  return headToScreen(s.yaw, s.pitch, state.neutral, +S.range, innerWidth, innerHeight);
}
function setNeutral(samples) {
  const n = samples.length;
  state.neutral = { yaw: samples.reduce((a, s) => a + s.yaw, 0) / n, pitch: samples.reduce((a, s) => a + s.pitch, 0) / n };
  state.offset = { x: 0, y: 0 };
  if (S.cal[S.mode]) {
    // Calibrated: shift so the current pose lands in the middle of the screen.
    const pts = samples.map(mapToScreen);
    state.offset = { x: innerWidth / 2 - pts.reduce((a, p) => a + p[0], 0) / n, y: innerHeight / 2 - pts.reduce((a, p) => a + p[1], 0) / n };
  }
  filterX.reset(); filterY.reset();
}

async function recenter() {
  if (S.mode === 'mouse') { toast('Recenter is for head and eye pointing.'); return; }
  if (!state.cameraOn && !(await startCamera())) return;
  const box = $('calib'), dotEl = $('calibDot'), msg = $('calibMsg');
  state.calibrating = true; box.classList.add('show');
  msg.innerHTML = 'Look at the dot and keep still<small>Recentering…</small>';
  Object.assign(dotEl.style, { display: 'block', left: '50%', top: '50%' });
  await wait(700);
  const got = [];
  const end = performance.now() + 700;
  while (performance.now() < end) { if (state.sample?.face) got.push(state.sample); await wait(33); }
  dotEl.style.display = 'none'; box.classList.remove('show'); state.calibrating = false;
  if (got.length < 6) { toast("I couldn't see your face. Try again facing the camera."); return; }
  setNeutral(got); toast('Pointer recentered');
}

// ---------- calibration ----------
const CAL_POINTS = [[.08, .1], [.5, .1], [.92, .1], [.92, .5], [.5, .5], [.08, .5], [.08, .9], [.5, .9], [.92, .9]];
async function calibrate() {
  if (S.mode === 'mouse') { toast('Calibration is for head and eye pointing.'); return; }
  if (!state.cameraOn && !(await startCamera())) return;
  closeSettings();
  const box = $('calib'), dotEl = $('calibDot'), msg = $('calibMsg');
  state.calibrating = true; box.classList.add('show');
  let cancelled = false;
  const onKey = (e) => { if (e.key === 'Escape') cancelled = true; };
  addEventListener('keydown', onKey);
  msg.innerHTML = S.mode === 'eyes'
    ? 'Keep your head still and follow the red dot with your eyes.<small>Nine dots, about 15 seconds. Press Esc to stop.</small>'
    : 'Point your nose at the red dot as it moves.<small>Nine dots, about 15 seconds. Press Esc to stop.</small>';
  await wait(2600);
  msg.innerHTML = '';
  const samples = []; let seen = 0, total = 0;
  for (const [x, y] of CAL_POINTS) {
    if (cancelled) break;
    Object.assign(dotEl.style, { display: 'block', left: x * 100 + '%', top: y * 100 + '%' });
    dotEl.classList.remove('collect');
    await wait(850);
    dotEl.classList.add('collect');
    const end = performance.now() + 850;
    while (performance.now() < end) {
      total++;
      if (state.sample?.face && state.sample.blink < 0.35) { samples.push({ f: features(state.sample), x, y }); seen++; }
      await wait(33);
    }
  }
  dotEl.style.display = 'none';
  removeEventListener('keydown', onKey);
  let result = null;
  if (!cancelled && seen > total * 0.4) result = fitCalibration(samples);
  if (result) {
    S.cal = { ...S.cal, [S.mode]: result }; save();
    state.offset = { x: 0, y: 0 }; filterX.reset(); filterY.reset();
    const grade = calibrationGrade(result.error);
    msg.innerHTML = `Calibration is ${grade}.<small>Average error is about ${(result.error * 100).toFixed(1)}% of the screen.${grade === 'poor' || grade === 'fair' ? ' Better light and sitting still will help. You can run it again any time.' : ''}</small>`;
  } else {
    msg.innerHTML = cancelled ? 'Calibration stopped.' : "Calibration didn't work: I lost sight of your face.<small>Face the camera with light in front of you, then try again.</small>";
  }
  await wait(2400);
  box.classList.remove('show'); state.calibrating = false;
  refreshCalInfo();
}
function refreshCalInfo() {
  const c = S.cal[S.mode];
  $('calInfo').textContent = S.mode === 'mouse' ? '' : c
    ? `Calibrated for ${S.mode === 'eyes' ? 'eyes' : 'head'}: ${calibrationGrade(c.error)} (about ${(c.error * 100).toFixed(1)}% average error).`
    : S.mode === 'eyes' ? 'Eye pointing needs calibration. Choose Calibrate.' : 'Not calibrated. Head pointing works without it; calibrating fits it to you.';
}
const wait = (ms) => new Promise(r => setTimeout(r, ms));

// ---------- microphone switch ----------
let micStarted = false;
async function startMic() {
  if (micStarted) return true;
  try {
    if (bridge && !(await bridge.media.ask('microphone'))) throw new Error('denied');
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: false } });
    const ctx = synth.ensure();
    const an = ctx.createAnalyser(); an.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Float32Array(an.fftSize);
    const tick = () => {
      an.getFloatTimeDomainData(buf);
      let sum = 0; for (const v of buf) sum += v * v;
      const r = onset.push(Math.sqrt(sum / buf.length), performance.now(), +S.mic);
      $('micMeter').value = r.level;
      const m = $('obMicMeter'); if (m) m.value = r.level;
      if (r.hit) onSwitch('sound');
      requestAnimationFrame(tick);
    };
    tick(); micStarted = true; return true;
  } catch {
    toast('Microphone access is off. Allow it in System Settings › Privacy & Security › Microphone.', 5000);
    return false;
  }
}

// ---------- targeting ----------
const isPad = (t) => t?.dataset.pad != null;
const isHoldable = (t) => isPad(t) || t?.dataset.hui === 'rewind' || t?.dataset.hui === 'fastForward';
const usable = (el) => el && !el.classList.contains('disabled') && el.offsetParent !== null;
// The target under the pointer, or (magnetic targeting) the nearest one within reach, so the
// gaps between targets are never dead zones.
const MAGNET_PX = 70;
function targetAt(x, y) {
  const el = document.elementFromPoint(x, y)?.closest('.target');
  if (usable(el)) return el;
  const layer = document.querySelector('#onboard.show, #pauseOverlay.show') || document.querySelector('main');
  let best = null, bestD = MAGNET_PX;
  for (const t of layer.querySelectorAll('.target')) {
    if (!usable(t)) continue;
    const r = t.getBoundingClientRect();
    const d = Math.hypot(Math.max(r.left - x, 0, x - r.right), Math.max(r.top - y, 0, y - r.bottom));
    if (d < bestD) { best = t; bestD = d; }
  }
  return best;
}
function inflated(t, pad) {
  const r = t.getBoundingClientRect();
  return state.px > r.left - pad && state.px < r.right + pad && state.py > r.top - pad && state.py < r.bottom + pad;
}
function setCurrent(t, now) {
  if (state.current === t) return;
  if (state.current) {
    state.current.classList.remove('gazed'); setProgress(state.current, 0);
    if (state.fired && isHoldable(state.current) && !(S.select === 'switch' && switchDown)) release(state.current);
  }
  state.current = t; state.enteredAt = now; state.fired = false;
  if (t) t.classList.add('gazed');
}
function setProgress(t, p) {
  const bar = t.querySelector(':scope > .progress');
  if (bar) bar.style.width = clamp(p, 0, 1) * 100 + '%';
  $('cursorFill').setAttribute('stroke-dasharray', `${clamp(p, 0, 1) * 126} 126`);
}

function frame(now) {
  requestAnimationFrame(frame);
  const cursor = $('cursor');
  // Camera modes wait for the automatic centring (about the first second) before anything can fire.
  const active = S.mode === 'mouse' || (state.cameraOn && state.autoCentre === null);
  cursor.style.display = active && !state.calibrating ? 'block' : 'none';
  cursor.style.transform = `translate(${state.px}px, ${state.py}px)`;
  const lost = S.mode !== 'mouse' && state.lostSince && now - state.lostSince > 300;
  cursor.classList.toggle('lost', !!lost);
  cursor.classList.toggle('paused', state.paused);
  showFaceBanner(S.mode !== 'mouse' && state.cameraOn && state.lostSince && now - state.lostSince > 900);
  if (!active || state.calibrating || state.settingsOpen) { setCurrent(null, now); return; }
  if (lost) {
    // Never fire while the face is lost; let go of held notes after half a second.
    if (state.current) { setProgress(state.current, 0); state.enteredAt = now; }
    if (now - state.lostSince > 500 && state.current) setCurrent(null, now);
    return;
  }

  // Sticky targeting: switch targets only after the pointer has settled on a new one,
  // and keep the current target while the pointer crosses the gap between targets.
  const hit = targetAt(state.px, state.py);
  if (hit !== state.current) {
    if (!hit && state.current && inflated(state.current, 30)) { /* in the gutter: stay */ }
    else {
      if (state.candidate !== hit) { state.candidate = hit; state.candidateSince = now; }
      const settle = isPad(hit) || isPad(state.current) ? 45 : 90;
      if (now - state.candidateSince >= settle) setCurrent(hit, now);
    }
  } else state.candidate = hit;

  const t = state.current;
  if (!t) { setProgress(document.body, 0); return; }
  if (S.select === 'dwell' && !state.fired) {
    const need = isPad(t) ? +S.padDwell : +S.dwell;
    const p = need <= 0 ? 1 : (now - state.enteredAt) / need;
    setProgress(t, p);
    if (p >= 1) { press(t, 'gaze'); state.fired = true; setProgress(t, 0); }
  } else if (S.select === 'blink' && !state.fired && state.sample?.face) {
    if (state.sample.blink > 0.5) {
      state.blinkSince ||= now;
      setProgress(t, (now - state.blinkSince) / +S.blink);
      if (now - state.blinkSince >= +S.blink) { press(t, 'gaze'); state.fired = true; state.blinkSince = 0; setProgress(t, 0); }
    } else { state.blinkSince = 0; setProgress(t, 0); }
  } else if (!state.fired) setProgress(t, 0);
}

function showFaceBanner(show) {
  const b = $('faceBanner');
  if (show && !b.classList.contains('show')) {
    const s = state.sample;
    $('faceBannerText').textContent = s && s.brightness < 0.18
      ? "I can't see your face: it's too dark. Turn on a light in front of you."
      : "I can't see your face. Move back into view of the camera.";
  }
  b.classList.toggle('show', !!show);
}

// ---------- switch / sound input ----------
let switchDown = false;
const IGNORE_KEYS = new Set(['Tab', 'Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Escape']);
addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || IGNORE_KEYS.has(e.key)) return;
  if (state.onboardStep === 'select' && S.select === 'switch') { markTest(`Got it: “${e.key === ' ' ? 'Space' : e.key}”`); }
  if (S.select !== 'switch' || state.settingsOpen || e.target.closest?.('select, input')) return;
  e.preventDefault();
  if (e.repeat || switchDown) return;
  switchDown = true; onSwitch('switch');
});
addEventListener('keyup', (e) => {
  if (S.select !== 'switch' || !switchDown) return;
  switchDown = false;
  if (state.current && state.fired && isHoldable(state.current)) release(state.current);
});
function onSwitch(kind) {
  if (state.onboardStep === 'select' && kind === 'sound' && S.select === 'sound') markTest('Heard it!');
  if (S.select !== kind || !state.current || state.calibrating || state.settingsOpen) return;
  const t = state.current;
  if (kind === 'sound' && state.fired && isPad(t) && !S.hold) release(t);   // retrigger on each sound
  press(t, 'gaze'); state.fired = true;
}

// Mouse, touch and keyboard always work too (for helpers and for testing).
document.addEventListener('pointerdown', (e) => {
  const t = e.target.closest('.target'); if (!t || e.button !== 0) return;
  if (state.current === t) state.fired = true;   // a click counts; don't let dwell fire it again
  press(t, 'mouse');
  try { t.setPointerCapture(e.pointerId); } catch {}
  const up = () => { release(t); t.removeEventListener('pointerup', up); t.removeEventListener('pointercancel', up); };
  t.addEventListener('pointerup', up); t.addEventListener('pointercancel', up);
});
document.addEventListener('click', (e) => {
  const cmd = e.target.closest('[data-cmd]'); if (cmd) { command(cmd.dataset.cmd); return; }
  const t = e.target.closest('.target');
  if (t && e.detail === 0) { press(t, 'key'); setTimeout(() => release(t), 250); }   // Enter / Space on a focused target
});
addEventListener('mousemove', (e) => { if (S.mode === 'mouse') { state.px = e.clientX; state.py = e.clientY; } });

// ---------- actions ----------
const sounding = new Map();   // midi note -> count (chords can share notes)
function notesOn(notes) {
  for (const n of notes) {
    sounding.set(n, (sounding.get(n) || 0) + 1);
    if (sounding.get(n) > 1) continue;
    if (S.builtIn) synth.noteOn(n, +S.velocity);
    midi.sendNotes([0x90, n, +S.velocity]);
  }
}
function notesOff(notes) {
  for (const n of notes) {
    const c = (sounding.get(n) || 0) - 1;
    if (c > 0) { sounding.set(n, c); continue; }
    sounding.delete(n); synth.noteOff(n); midi.sendNotes([0x80, n, 0]);
  }
}
function allNotesOff() {
  for (const n of [...sounding.keys()]) { synth.noteOff(n); midi.sendNotes([0x80, n, 0]); }
  sounding.clear(); synth.allOff(); midi.sendNotes([0xb0, 123, 0]);
  document.querySelectorAll('#pads .target.on').forEach(p => { p.classList.remove('on'); delete p.dataset.down; });
}

function feedback(t) {
  t.classList.add('flash'); setTimeout(() => t.classList.remove('flash'), 140);
  if (S.tick && !isPad(t)) synth.tick();
}

function press(t, source) {
  if (state.paused && t.dataset.action !== 'resume') return;
  if (isPad(t)) {
    const pad = pads[+t.dataset.pad]; if (!pad) return;
    if (S.hold) {
      if (t.classList.contains('on')) { notesOff(pad.notes); t.classList.remove('on'); }
      else { notesOn(pad.notes); t.classList.add('on'); }
      return;
    }
    if (t.dataset.down) return;
    t.dataset.down = '1'; notesOn(pad.notes); t.classList.add('on');
    return;
  }
  feedback(t);
  const d = t.dataset;
  if (d.goto) return showPage(d.goto);
  if (d.hui) {
    const port = HUI.PORT[d.hui];
    if (!midi.transport(port, true)) { toast('Not connected to Pro Tools yet. See Settings › Pro Tools and MIDI.', 4000); return; }
    if (isHoldable(t)) { state.heldHui = { t, port }; if (source !== 'gaze' && source !== 'mouse') setTimeout(() => release(t), 400); }
    else setTimeout(() => midi.transport(port, false), 90);
    return;
  }
  if (d.action) return action(d.action, t);
  if (d.ob) return onboardAction(d.ob, t);
  if (d.practice != null) { t.classList.add('done'); state.practiceDone.add(d.practice); renderPracticeState(); }
}
function release(t) {
  if (isPad(t)) {
    if (S.hold || !t.dataset.down) return;
    delete t.dataset.down; notesOff(pads[+t.dataset.pad]?.notes || []); t.classList.remove('on');
    return;
  }
  if (state.heldHui && state.heldHui.t === t) { midi.transport(state.heldHui.port, false); state.heldHui = null; }
}

function action(a) {
  switch (a) {
    case 'pause': return setPaused(true);
    case 'resume': return setPaused(false);
    case 'octdown': S.octave = Math.max(1, S.octave - 1); break;
    case 'octup': S.octave = Math.min(7, S.octave + 1); break;
    case 'scale': { const k = Object.keys(SCALES); S.scale = k[(k.indexOf(S.scale) + 1) % k.length]; break; }
    case 'chords': S.chords = !S.chords; break;
    case 'hold': S.hold = !S.hold; if (!S.hold) allNotesOff(); break;
    case 'sound': { const k = Object.keys(SYNTH_PRESETS); S.preset = k[(k.indexOf(S.preset) + 1) % k.length]; synth.setPreset(S.preset); break; }
    case 'panic': allNotesOff(); toast('All notes off'); return;
  }
  save(); if (a !== 'hold' && a !== 'sound') allNotesOff();
  renderInstrument(); syncSettingsForm();
}

function setPaused(p) {
  state.paused = p; $('pauseOverlay').classList.toggle('show', p);
  if (p) { allNotesOff(); if (state.heldHui) release(state.heldHui.t); }
  toast(p ? 'Paused. Look at Resume to continue.' : 'Resumed');
}

function showPage(id) {
  allNotesOff();
  state.page = id;
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === id));
  document.querySelectorAll('.tabs [data-goto]').forEach(b => b.setAttribute('aria-current', b.dataset.goto === id ? 'page' : 'false'));
}

// ---------- instrument page ----------
let pads = [];
function renderInstrument() {
  pads = buildPads({ key: +S.key, octave: +S.octave, scale: S.scale, count: +S.pads, chords: S.chords });
  const cols = +S.pads === 6 ? 3 : 4, rows = Math.ceil(pads.length / cols);
  const grid = $('pads'); grid.innerHTML = '';
  grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`; grid.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
  // Highest notes on the top row, so looking up means going up in pitch.
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const i = (rows - 1 - r) * cols + c; const p = pads[i]; if (!p) continue;
      const b = document.createElement('button');
      b.className = 'target' + (p.isRoot ? ' root' : ''); b.dataset.pad = i;
      b.setAttribute('aria-label', `Play ${p.label}`);
      b.innerHTML = `${p.label}<small>${p.sub || '&nbsp;'}</small><span class="progress"></span>`;
      grid.appendChild(b);
    }
  $('octLabel').textContent = NOTE_NAMES[+S.key] + S.octave;
  $('scaleLabel').textContent = `${NOTE_NAMES[+S.key]} ${S.scale}`;
  $('chordsLabel').textContent = S.chords ? 'on' : 'off';
  $('holdLabel').textContent = S.hold ? 'on' : 'off';
  $('soundLabel').textContent = S.builtIn ? SYNTH_PRESETS[S.preset] : 'MIDI only';
  document.querySelector('[data-action=chords]').setAttribute('aria-pressed', S.chords);
  document.querySelector('[data-action=hold]').setAttribute('aria-pressed', S.hold);
}
function addProgressBars(root = document) {
  root.querySelectorAll('.target').forEach(t => { if (!t.querySelector(':scope > .progress')) t.insertAdjacentHTML('beforeend', '<span class="progress"></span>'); });
}

// ---------- Pro Tools LEDs ----------
midi.addEventListener('led', (e) => {
  const { zone, port, on } = e.detail;
  if (zone !== HUI.TRANSPORT_ZONE) return;
  if (port === HUI.PORT.play) { $('tPlay').classList.toggle('lit', on); $('tPlayState').textContent = on ? 'playing' : 'Pro Tools play'; }
  if (port === HUI.PORT.record) { $('tRec').classList.toggle('lit', on); $('tRecState').textContent = on ? 'record armed' : 'record arm the transport'; }
});
midi.addEventListener('change', () => { refreshChips(); renderMidiSettings(); });

// ---------- settings drawer ----------
function openSettings() {
  state.settingsOpen = true; syncSettingsForm(); renderMidiSettings(); refreshCalInfo();
  $('settings').classList.add('open'); $('settings').setAttribute('aria-hidden', 'false');
  $('closeSettings').focus();
  if (S.select === 'sound') startMic();
}
function closeSettings() {
  state.settingsOpen = false; $('settings').classList.remove('open'); $('settings').setAttribute('aria-hidden', 'true');
}
$('settingsBtn').onclick = openSettings; $('closeSettings').onclick = closeSettings;
$('recenterBtn').onclick = recenter; $('calibBtn').onclick = calibrate;
addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.settingsOpen) closeSettings(); });

const FORM = {
  sMode: 'mode', sRange: 'range', sSmooth: 'smooth', sCamera: 'camera', sPreview: 'preview',
  sSelect: 'select', sDwell: 'dwell', sPadDwell: 'padDwell', sBlink: 'blink', sMic: 'mic', sTick: 'tick',
  sBuiltIn: 'builtIn', sPreset: 'preset', sVolume: 'volume', sKey: 'key', sScale: 'scale', sPads: 'pads', sVelocity: 'velocity',
  sTheme: 'theme', sContrast: 'contrast', sSize: 'size', sSpacing: 'spacing', sOnTop: 'onTop',
};
for (const [k, v] of Object.entries(SYNTH_PRESETS)) $('sPreset').add(new Option(v, k));
NOTE_NAMES.forEach((n, i) => $('sKey').add(new Option(n, i)));
Object.keys(SCALES).forEach(n => $('sScale').add(new Option(n, n)));
function syncSettingsForm() {
  for (const [id, key] of Object.entries(FORM)) {
    const el = $(id); if (el.type === 'checkbox') el.checked = !!S[key]; else el.value = S[key];
  }
  $('sDwellOut').textContent = (S.dwell / 1000).toFixed(2) + ' s';
  $('sPadDwellOut').textContent = +S.padDwell === 0 ? 'instant' : (S.padDwell / 1000).toFixed(2) + ' s';
  $('sBlinkOut').textContent = (S.blink / 1000).toFixed(2) + ' s';
  $('sModeHelp').textContent = {
    head: 'Turn your head to move. Works right away; Recenter if it drifts.',
    eyes: 'Look where you want to go. Needs calibration and a steady head.',
    mouse: 'Use a mouse, trackpad, joystick, head mouse or the macOS Head Pointer, with dwell or a switch to select.',
  }[S.mode];
}
for (const [id, key] of Object.entries(FORM)) {
  const el = $(id);
  const handler = () => {
    const v = el.type === 'checkbox' ? el.checked : el.type === 'range' ? +el.value : el.value;
    S[key] = v; save(); onSettingChanged(key);
    syncSettingsForm();
  };
  el.addEventListener(el.type === 'range' ? 'input' : 'change', handler);
}
async function onSettingChanged(key) {
  switch (key) {
    case 'smooth': filterX.setSmoothing(S.smooth); filterY.setSmoothing(S.smooth); break;
    case 'mode': filterX.reset(); filterY.reset(); state.offset = { x: 0, y: 0 }; if (S.mode !== 'mouse') await startCamera(); refreshCalInfo(); break;
    case 'camera': if (state.cameraOn) { await tracker.open(S.camera); for (const v of document.querySelectorAll('video[data-mirror]')) v.srcObject = tracker.stream; } break;
    case 'select': if (S.select === 'sound') await startMic(); if (S.select === 'blink' && !state.cameraOn) await startCamera(); break;
    case 'builtIn': if (!S.builtIn) synth.allOff(); renderInstrument(); break;
    case 'preset': synth.setPreset(S.preset); renderInstrument(); break;
    case 'volume': synth.setVolume(+S.volume); break;
    case 'key': case 'scale': case 'pads': allNotesOff(); renderInstrument(); break;
  }
  applyDisplay(); refreshChips();
}
$('clearCal').onclick = () => { S.cal = { ...S.cal, [S.mode]: undefined }; delete S.cal[S.mode]; save(); state.offset = { x: 0, y: 0 }; refreshCalInfo(); toast('Calibration cleared'); };
$('resetAll').onclick = () => {
  if (!confirm('Reset every GazeStage setting, including calibration?')) return;
  try { localStorage.removeItem(KEY); } catch {}
  location.reload();
};

function renderMidiSettings() {
  const native = midi.mode === 'native';
  $('midiNative').style.display = native ? '' : 'none';
  $('midiWeb').style.display = native ? 'none' : '';
  if (native) return;
  const fill = (id, kind, none) => {
    const sel = $(id), list = midi.ports(kind);
    sel.innerHTML = ''; sel.add(new Option(none, ''));
    list.forEach(p => sel.add(new Option(p.name, p.id)));
    sel.value = list.some(p => p.id === midi.sel[kind]) ? midi.sel[kind] : '';
    sel.onchange = () => midi.choose(kind, sel.value);
  };
  fill('sOutHui', 'huiOut', 'Not connected'); fill('sInHui', 'huiIn', 'Not connected'); fill('sOutNotes', 'notes', 'Not connected');
  const win = bridge?.platform === 'win32' || /Windows/.test(navigator.userAgent);
  $('midiWebSteps').innerHTML = (win
    ? ['Open <b>MIDI Settings</b> (Windows 11) or install the free <b>loopMIDI</b>.', 'Create three ports: <code>To Pro Tools</code>, <code>From Pro Tools</code> and <code>GazeStage Notes</code>.']
    : ['Open <b>Audio MIDI Setup</b>, choose Window › Show MIDI Studio, and turn on the <b>IAC Driver</b>.', 'Add three ports: <code>To Pro Tools</code>, <code>From Pro Tools</code> and <code>GazeStage Notes</code>.'])
    .concat(['GazeStage picks them up by name. In Pro Tools, add a <b>HUI</b> receiving from <code>To Pro Tools</code> and sending to <code>From Pro Tools</code>.'])
    .map(s => `<li>${s}</li>`).join('');
}

// ---------- menu commands ----------
function command(cmd) {
  switch (cmd) {
    case 'settings': return state.settingsOpen ? closeSettings() : openSettings();
    case 'recenter': return recenter();
    case 'calibrate': return calibrate();
    case 'pause': return setPaused(!state.paused);
    case 'page:transport': return showPage('transport');
    case 'page:play': return showPage('play');
    case 'panic': return allNotesOff();
    case 'onboarding': closeSettings(); return startOnboarding();
    case 'toggle-on-top': S.onTop = !S.onTop; save(); applyDisplay(); return toast(S.onTop ? 'GazeStage stays on top' : 'GazeStage no longer stays on top');
    case 'toggle-preview': S.preview = !S.preview; save(); return applyDisplay();
  }
}
bridge?.onCommand(command);

// ---------- guided setup ----------
const STEPS = ['welcome', 'camera', 'pointer', 'select', 'practice', 'done'];
function startOnboarding() { $('onboard').classList.add('show'); renderStep('welcome'); }
function finishOnboarding(page) {
  S.onboarded = true; save();
  $('onboard').classList.remove('show'); state.onboardStep = null;
  showPage(page); refreshChips();
}
function stepper(step) {
  const i = STEPS.indexOf(step);
  return `<div class="stepper" aria-hidden="true">${STEPS.map((_, k) => `<span class="${k <= i ? 'done' : ''}"></span>`).join('')}</div>`;
}
function choice(ob, value, title, sub, chosen, badge) {
  return `<button class="target${chosen ? ' chosen' : ''}" data-ob="${ob}" data-value="${value}" role="radio" aria-checked="${chosen}">${title}${badge ? ` <span class="badge">${badge}</span>` : ''}<small>${sub}</small></button>`;
}
function actions(back, nextLabel, nextOb = 'next', extra = '') {
  return `<div class="actions">${back ? '<button class="target" data-ob="back">Back</button>' : '<span></span>'}${extra}<button class="target primary" data-ob="${nextOb}">${nextLabel}</button></div>`;
}

function renderStep(step) {
  state.onboardStep = step;
  const card = $('onboardCard');
  let html = stepper(step);
  if (step === 'welcome') {
    html += `<h1>Welcome to GazeStage</h1>
      <p class="lead">Play music and run Pro Tools with your head, your eyes, a sound or a switch. This takes about two minutes. Everything stays on this computer: nothing is recorded or sent anywhere.</p>
      <div class="note">A helper can click through these steps with a mouse. Once the camera is on, you can also select everything here by looking at it and holding still.</div>
      <div class="actions"><button class="target" data-ob="skip">Skip setup</button><button class="target primary" data-ob="next">Get started</button></div>`;
  } else if (step === 'camera') {
    html += `<h2>Turn on the camera</h2>
      <p class="lead">GazeStage follows your head and eyes with the camera. Sit about an arm's length from the screen with your face in the oval.</p>
      <div class="camstage"><div class="bigcam"><video data-mirror playsinline muted></video><div class="guide" id="obGuide"></div></div>
      <ul class="checks">
        <li id="ckFace"><span class="dot"></span><span>Face found<small>Look toward the screen.</small></span></li>
        <li id="ckLight"><span class="dot"></span><span>Enough light<small>Light in front of you works best, not a bright window behind.</small></span></li>
        <li id="ckCentre"><span class="dot"></span><span>Centred<small>Keep your face in the middle of the picture.</small></span></li>
        <li id="ckDist"><span class="dot"></span><span>Good distance<small>About an arm's length away.</small></span></li>
      </ul></div>
      <p id="camMsg" class="lead" style="margin:0 0 12px"></p>
      ${actions(true, state.cameraOn ? 'Continue' : 'Turn on camera', state.cameraOn ? 'next' : 'camera', '<button class="target" data-ob="nocam">Use a mouse instead</button>')}`;
  } else if (step === 'pointer') {
    html += `<h2>How do you want to point?</h2><p class="lead">You can change this any time in Settings.</p>
      <div class="choices">
        ${choice('mode', 'head', 'My head', 'Turn your head a little to move. Steady and works right away.', S.mode === 'head', 'Recommended')}
        ${choice('mode', 'eyes', 'My eyes', 'Look where you want to go. Needs a short calibration and a still head.', S.mode === 'eyes')}
        ${choice('mode', 'mouse', 'Mouse or another pointer', 'Mouse, trackpad, joystick, head mouse or the macOS Head Pointer.', S.mode === 'mouse')}
      </div>
      <div class="row" style="max-width:520px"><label for="obRange">Head movement needed</label><select id="obRange"><option value="10">Small</option><option value="16">Medium</option><option value="24">Large</option></select></div>
      ${actions(true, 'Continue')}`;
  } else if (step === 'select') {
    html += `<h2>How do you want to select?</h2><p class="lead">Point at something, then select it one of these ways.</p>
      <div class="choices">
        ${choice('select', 'dwell', 'Look and hold', 'Keep pointing at it for a moment. Nothing else needed.', S.select === 'dwell', 'Recommended')}
        ${choice('select', 'switch', 'Switch or key', 'Any key, adaptive switch, foot pedal or Xbox Adaptive Controller button.', S.select === 'switch')}
        ${choice('select', 'sound', 'A short sound', 'A pop, click or “ta” into the microphone. Great for rhythm.', S.select === 'sound')}
        ${choice('select', 'blink', 'A long blink', 'Close both eyes a little longer than a normal blink.', S.select === 'blink')}
      </div>
      <div class="note" id="obTest">${selectTestText()}</div>
      ${actions(true, 'Continue')}`;
  } else if (step === 'practice') {
    state.practiceDone = new Set();
    html += `<h2>Try it</h2><p class="lead">Select each of the three targets. ${S.select === 'dwell' ? 'Point at one and hold still until the ring fills.' : S.select === 'switch' ? 'Point at one and press your switch.' : S.select === 'sound' ? 'Point at one and make your sound.' : 'Point at one and close your eyes for a moment.'}</p>
      <div class="practice"><button class="target" data-practice="1">One</button><button class="target" data-practice="2">Two</button><button class="target" data-practice="3">Three</button></div>
      <p id="practiceMsg" class="lead" style="margin:0 0 12px"></p>
      ${actions(true, 'Continue', 'next', S.mode !== 'mouse' ? `<button class="target" data-ob="recenter">Recenter</button><button class="target" data-ob="calibrate">Calibrate${S.mode === 'eyes' ? '' : ' (optional)'}</button>` : '')}`;
  } else if (step === 'done') {
    const native = midi.mode === 'native';
    html += `<h2>You're ready</h2>
      <p class="lead">Play the built-in instrument straight away. To control Pro Tools, connect it once:</p>
      <div class="note">${native
        ? '<ol class="steps" style="color:inherit"><li>In Pro Tools choose <b>Setup › Peripherals › MIDI Controllers</b>.</li><li>Add a <b>HUI</b> with Receive From and Send To set to <code>GazeStage HUI</code>.</li><li>For instruments, set an instrument track\'s input to <code>GazeStage Notes</code>.</li></ol>'
        : 'Open Settings › Pro Tools and MIDI to choose your loopback ports.'}</div>
      <div class="actions"><button class="target" data-ob="finish-transport">Go to Transport</button><button class="target primary" data-ob="finish-play">Start playing</button></div>`;
  }
  card.innerHTML = html;
  addProgressBars(card);
  if (step === 'camera') { for (const v of card.querySelectorAll('video[data-mirror]')) { v.srcObject = tracker.stream || null; v.play?.().catch(() => {}); } }
  if (step === 'pointer') { const r = $('obRange'); r.value = S.range; r.onchange = () => { S.range = r.value; save(); }; }
  if (step === 'select' && S.select === 'sound') startMic();
}

function selectTestText() {
  return {
    dwell: 'Tip: you can change how long to hold in Settings.',
    switch: 'Press your switch or any key now to test it.',
    sound: 'Make a short pop or click sound now to test it. <meter id="obMicMeter" min="0" max="1" value="0" style="width:160px;vertical-align:middle"></meter>',
    blink: 'Close both eyes a little longer than a normal blink to test it.',
  }[S.select];
}
function markTest(text) { const el = $('obTest'); if (el) el.innerHTML = `<b style="color:var(--ok)">✓ ${text}</b>`; }
function renderPracticeState() {
  const m = $('practiceMsg'); if (!m) return;
  m.innerHTML = state.practiceDone.size >= 3 ? '<b style="color:var(--ok)">✓ Nicely done.</b>' : `${state.practiceDone.size} of 3`;
}

function updateOnboardChecks(s) {
  if (state.onboardStep !== 'camera') return;
  const set = (id, ok) => { const d = $(id)?.querySelector('.dot'); if (d) d.className = 'dot ' + (ok == null ? '' : ok ? 'ok' : 'warn'); };
  set('ckFace', s.face); set('ckLight', s.brightness > 0.2);
  set('ckCentre', s.face ? s.offCentre < 0.4 : null); set('ckDist', s.face ? s.size > 0.16 && s.size < 0.62 : null);
  const good = s.face && s.brightness > 0.2 && s.offCentre < 0.4 && s.size > 0.16 && s.size < 0.62;
  $('obGuide')?.classList.toggle('ok', !!good);
}

async function onboardAction(ob, t) {
  const step = state.onboardStep, i = STEPS.indexOf(step);
  if (ob === 'skip') return finishOnboarding('transport');
  if (ob === 'back') return renderStep(STEPS[Math.max(0, i - 1)]);
  if (ob === 'camera') {
    $('camMsg').textContent = 'Starting the camera…';
    const ok = await startCamera();
    if (ok) return renderStep('camera');
    $('camMsg').innerHTML = state.cameraError === 'denied'
      ? 'Camera access is off for GazeStage. <button class="linkish" id="obOpenCam">Open System Settings</button>, turn on GazeStage under Camera, then reopen the app.'
      : `The camera couldn't start (${state.cameraError}). Check it isn't in use by another app.`;
    $('obOpenCam')?.addEventListener('click', () => bridge?.media.openSettings('camera'));
    return;
  }
  if (ob === 'nocam') { S.mode = 'mouse'; save(); return renderStep('select'); }
  if (ob === 'mode') { S.mode = t.dataset.value; save(); filterX.reset(); filterY.reset(); if (S.mode !== 'mouse') startCamera(); return renderStep('pointer'); }
  if (ob === 'select') {
    S.select = t.dataset.value; save(); refreshChips();
    if (S.select === 'sound') await startMic();
    return renderStep('select');
  }
  if (ob === 'recenter') return recenter();
  if (ob === 'calibrate') { await calibrate(); return; }
  if (ob === 'finish-play') return finishOnboarding('play');
  if (ob === 'finish-transport') return finishOnboarding('transport');
  if (ob === 'next') {
    const next = STEPS[i + 1];
    if (next === 'practice' && S.mode !== 'mouse') {
      renderStep('practice');
      if (S.mode === 'eyes' && !S.cal.eyes) await calibrate(); else await recenter();
      return;
    }
    return renderStep(next);
  }
}

// ---------- start ----------
applyDisplay(); syncSettingsForm(); renderInstrument(); addProgressBars(); refreshChips(); refreshCalInfo();
$('aboutLine').textContent = 'GazeStage 0.3 · Limitless Sound · runs entirely on this computer.';
synth.setVolume(+S.volume);
midi.init();
requestAnimationFrame(frame);
(async () => {
  if (!S.onboarded) { startOnboarding(); return; }
  if (S.mode !== 'mouse') {
    const st = bridge ? await bridge.media.status() : { camera: 'granted' };
    if (st.camera === 'granted' || st.camera === 'not-determined') await startCamera();
    else toast('Camera access is off. Turn it on in System Settings › Privacy & Security › Camera.', 6000);
  }
  if (S.select === 'sound') startMic();
})();
