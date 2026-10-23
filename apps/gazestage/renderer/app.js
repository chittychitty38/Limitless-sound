// GazeStage app: pointer, targeting, selection, pages, guided setup and settings.
import {
  displayInUse, shownProgress, languageInUse, TEXT_SCALE,
  OneEuro, fitCalibration, calibrationGrade, dot, headToScreen, buildPads, SCALES, NOTE_NAMES, HUI, OnsetDetector,
  XY_PROFILES, xyMessages, XYMotion, toCC,
} from './lib.js';
import { Tracker } from './tracker.js';
import { Synth, SYNTH_PRESETS } from './synth.js';
import { SynthLink } from './synth-link.js';
import { MidiRouter } from './midi.js';

const $ = (id) => document.getElementById(id);
const bridge = window.gazestage || null;
if (bridge?.platform === 'darwin') document.body.classList.add('mac');

// ---------- language ----------
// GazeStage's words in the suite's language while Limitless Sound runs, else in the computer's
// (languageInUse in lib.js). The Spanish is in index.html (strings-es), English text → Spanish.
const STRINGS = { es: JSON.parse($('strings-es').textContent) };
let lang = 'en';
function t(text, vars = {}) {
  let out = (STRINGS[lang] || {})[text] || text;
  for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(v);
  return out;
}
// The page's own words, kept in English so they can be put back. A sentence with bold words in
// it is one entry (data-html), so it can follow the other language's word order.
const fixedText = [], fixedAttrs = [], fixedHtml = [];
{
  for (const e of document.querySelectorAll('[data-html]')) fixedHtml.push([e, e.innerHTML.trim()]);
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode())
    if (n.nodeValue.trim() && !n.parentElement.closest('script, [data-html]')) fixedText.push([n, n.nodeValue]);
  for (const name of ['aria-label', 'title'])
    for (const e of document.querySelectorAll(`[${name}]`)) fixedAttrs.push([e, name, e.getAttribute(name)]);
}
const computerLanguages = () => (navigator.languages?.length ? navigator.languages : [navigator.language]);
function setLanguage(next) {
  next = STRINGS[next] ? next : 'en';
  if (next === lang) return false;
  lang = next;
  document.documentElement.lang = lang;   // screen readers read the page in it
  for (const [n, en] of fixedText) n.nodeValue = en.replace(en.trim(), t(en.trim()));
  for (const [e, name, en] of fixedAttrs) e.setAttribute(name, t(en));
  for (const [e, en] of fixedHtml) e.innerHTML = t(en);
  bridge?.setLanguage?.(lang);   // the menu, and the answers to other apps (main.js)
  return true;
}
setLanguage(languageInUse(null, computerLanguages()));
bridge?.setLanguage?.(lang);

// ---------- settings ----------
const DEFAULTS = {
  mode: 'head', range: '16', smooth: 5, camera: '', preview: true,
  select: 'dwell', dwell: 900, padDwell: 250, blink: 450, mic: 10, tick: true,
  builtIn: true, preset: 'keys', volume: 0.8, key: 0, scale: 'Major', pads: 8, velocity: 100, octave: 4, chords: false, hold: false,
  theme: 'dark', contrast: false, size: 'normal', spacing: 'normal', onTop: false,
  // Tone pad: where the point is, how it moves, and what it sends.
  xyX: 0.5, xyY: 0.5, xyFollow: false, xyGlide: 500, xyShape: true,
  xySnaps: { A: [0.2, 0.8], B: [0.8, 0.8], C: [0.2, 0.2], D: [0.8, 0.2] },
  xyOut: 'auto', xyProfile: 'learn', xyCcX: 16, xyCcY: 17, xyChannel: 1, xyNameX: 'Brightness', xyNameY: 'Room',
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
  xyStore: false, xyAnchor: null, nudging: null, teaching: null, listen: null,
  xySent: { x: toCC(S.xyX), y: toCC(S.xyY) },
};
const motion = new XYMotion(S.xyX, S.xyY);
const filterX = new OneEuro(S.smooth), filterY = new OneEuro(S.smooth);
const tracker = new Tracker($('cam'), store);
// The built-in instrument plays in a hidden page of its own (synth-link.js), so starting the
// computer's audio never holds up this page; in a plain browser, here.
const synth = bridge?.synth ? new SynthLink(bridge.synth) : new Synth(); synth.setPreset(S.preset);
const midi = new MidiRouter(store);
const onset = new OnsetDetector();
window.__gs = { state, S, synth, midi, motion, suite: () => suiteOn, listening: () => !!mic };   // for the smoke test

// ---------- display ----------
// Text size, contrast and motion come from GazeStage's own settings (and the system's reduced
// motion), and while Limitless Sound is connected, from the musician's shared settings too.
const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
let shared = null, display = null, reported = '';
function applyDisplay() {
  const r = document.documentElement;
  display = displayInUse({ size: S.size, contrast: S.contrast, reduceMotion: systemMotion.matches }, shared);
  r.dataset.theme = S.theme; r.dataset.contrast = display.highContrast ? 'high' : 'normal';
  r.dataset.motion = display.reduceMotion ? 'reduce' : 'normal';
  r.style.setProperty('--scale', display.textScale); r.dataset.spacing = S.spacing;
  r.dataset.size = display.textScale > TEXT_SCALE.xlarge ? 'huge' : S.size;   // huge: the shared size, past Extra large
  $('preview').classList.toggle('hidden', !S.preview || !state.cameraOn);
  bridge?.setAlwaysOnTop(S.onTop);
  if (setLanguage(languageInUse(shared, computerLanguages()))) relabel();
  reportDisplay();
}
// Everything the script draws, again in a new language.
function relabel() {
  fillOptions(); syncSettingsForm(); refreshCalInfo(); refreshChips(); renderInstrument(); renderLeds();
  lastDrawn = ''; renderTone(); renderMidiSettings(); renderToneSettings();
  if (state.onboardStep) renderStep(state.onboardStep);
}
systemMotion.addEventListener('change', applyDisplay);

let toastTimer = 0;
function toast(msg, ms = 2600) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), ms);
}

// The chips are checked every second but written only when they change: rewriting them laid out
// and redrew the window every second, about 1.4% of the CPU on a Mac sitting idle.
function chip(id, level, html) {
  const c = $(id), dot = c.querySelector('.dot'), text = c.querySelector('span:last-child');
  put(dot, '_level', level || '', (v) => { dot.className = 'dot ' + v; });
  put(text, '_html', html, (v) => { text.innerHTML = v; });
}
function refreshChips() {
  const cam = {
    off: [S.mode === 'mouse' ? 'ok' : '', S.mode === 'mouse' ? t('Pointer <b>mouse</b>') : t('Camera <b>off</b>')],
    loading: ['warn', t('Camera <b>starting…</b>')],
    tracking: ['ok', t('Camera <b>tracking</b>')],
    noface: ['warn', t('Camera <b>no face</b>')],
    error: ['bad', t('Camera <b>unavailable</b>')],
  }[state.cameraState];
  chip('chipCamera', cam[0], cam[1]);
  chip('chipSelect', 'ok', { dwell: t('Select <b>Dwell</b>'), switch: t('Select <b>Switch</b>'), sound: t('Select <b>Sound</b>'), blink: t('Select <b>Blink</b>') }[S.select]);
  const ports = midi.canSendHui || midi.notesTarget;
  if (midi.mode === 'native') chip('chipMidi', 'ok', t('MIDI <b>GazeStage ports</b>'));
  else if (midi.mode === 'web') chip('chipMidi', ports ? 'ok' : 'warn', ports ? t('MIDI <b>connected</b>') : t('MIDI <b>choose ports</b>'));
  else chip('chipMidi', 'bad', t('MIDI <b>off</b>'));
  chip('chipPT', midi.proToolsConnected ? 'ok' : '', midi.proToolsConnected ? t('Pro Tools <b>linked</b>') : t('Pro Tools <b>not linked</b>'));
  const hint = $('transportHint');
  put(hint, '_html', midi.proToolsConnected ? t('Connected to Pro Tools.')
    : midi.mode === 'native' ? `${t('Not linked yet. In Pro Tools, add a HUI controller using <b>GazeStage HUI</b>.')} <button class="linkish" data-cmd="settings">${t('How to connect')}</button>`
    : `${t('Not linked yet.')} <button class="linkish" data-cmd="settings">${t('Choose the Pro Tools ports in Settings')}</button>`, (v) => { hint.innerHTML = v; });
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
    await Promise.all([tracker.load(), tracker.open(S.camera)]);   // the face model loads in its worker meanwhile
    tracker.onSample = onSample;
    tracker.start();
    state.cameraOn = true; state.cameraState = 'tracking'; state.autoCentre = [];
    applyDisplay(); fillCameras();
    for (const v of document.querySelectorAll('video[data-mirror]')) v.srcObject = tracker.stream;
    return true;
  } catch (e) {
    console.error(e); tracker.close();   // never leave the camera on when tracking can't start
    state.cameraState = 'error'; refreshChips();
    state.cameraError = e.name === 'NotAllowedError' || /denied|turned off/i.test(e.message) ? 'denied' : (e.message || String(e));
    return false;
  } finally { refreshChips(); }
}
async function fillCameras() {
  const sel = $('sCamera'); const cams = await Tracker.cameras();
  sel.length = 1;
  cams.forEach((c, i) => sel.add(new Option(c.label || t('Camera {n}', { n: i + 1 }), c.deviceId)));
  sel.value = cams.some(c => c.deviceId === S.camera) ? S.camera : '';
}

// One camera frame.
function onSample(s) {
  state.sample = s; wake();
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
  if (S.mode === 'mouse') { toast(t('Recenter is for head and eye pointing.')); return; }
  if (!state.cameraOn && !(await startCamera())) return;
  const box = $('calib'), dotEl = $('calibDot'), msg = $('calibMsg');
  state.calibrating = true; box.classList.add('show');
  msg.innerHTML = `${t('Look at the dot and keep still')}<small>${t('Recentering…')}</small>`;
  Object.assign(dotEl.style, { display: 'block', left: '50%', top: '50%' });
  await wait(700);
  const got = [];
  const end = performance.now() + 700;
  while (performance.now() < end) { if (state.sample?.face) got.push(state.sample); await wait(33); }
  dotEl.style.display = 'none'; box.classList.remove('show'); state.calibrating = false;
  if (got.length < 6) { toast(t("I couldn't see your face. Try again facing the camera.")); return; }
  setNeutral(got); toast(t('Pointer recentered'));
}

// ---------- calibration ----------
const CAL_POINTS = [[.08, .1], [.5, .1], [.92, .1], [.92, .5], [.5, .5], [.08, .5], [.08, .9], [.5, .9], [.92, .9]];
async function calibrate() {
  if (S.mode === 'mouse') { toast(t('Calibration is for head and eye pointing.')); return; }
  if (!state.cameraOn && !(await startCamera())) return;
  closeSettings();
  const box = $('calib'), dotEl = $('calibDot'), msg = $('calibMsg');
  state.calibrating = true; box.classList.add('show');
  let cancelled = false;
  const onKey = (e) => { if (e.key === 'Escape') cancelled = true; };
  addEventListener('keydown', onKey);
  msg.innerHTML = (S.mode === 'eyes' ? t('Keep your head still and follow the red dot with your eyes.') : t('Point your nose at the red dot as it moves.'))
    + `<small>${t('Nine dots, about 15 seconds. Press Esc to stop.')}</small>`;
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
    msg.innerHTML = `${t('Calibration is {grade}.', { grade: gradeName(grade) })}<small>${t('Average error is about {error}% of the screen.', { error: (result.error * 100).toFixed(1) })}`
      + `${grade === 'poor' || grade === 'fair' ? ' ' + t('Better light and sitting still will help. You can run it again any time.') : ''}</small>`;
  } else {
    msg.innerHTML = cancelled ? t('Calibration stopped.')
      : `${t("Calibration didn't work: I lost sight of your face.")}<small>${t('Face the camera with light in front of you, then try again.')}</small>`;
  }
  await wait(2400);
  box.classList.remove('show'); state.calibrating = false;
  refreshCalInfo();
}
function refreshCalInfo() {
  const c = S.cal[S.mode];
  $('calInfo').textContent = S.mode === 'mouse' ? '' : c
    ? t('Calibrated for {part}: {grade} (about {error}% average error).', { part: S.mode === 'eyes' ? t('eyes') : t('head'), grade: gradeName(calibrationGrade(c.error)), error: (c.error * 100).toFixed(1) })
    : S.mode === 'eyes' ? t('Eye pointing needs calibration. Choose Calibrate.') : t('Not calibrated. Head pointing works without it; calibrating fits it to you.');
}
const gradeName = (grade) => ({ great: t('great'), good: t('good'), fair: t('fair'), poor: t('poor') })[grade] || grade;
const wait = (ms) => new Promise(r => setTimeout(r, ms));

// ---------- microphone switch ----------
// Open only while the sound switch is chosen: a Mac shows its microphone light for as long as
// an app listens, and listening keeps the audio and a meter running. Trying the sound switch in
// the guided setup and then choosing dwell used to leave the microphone on all session.
// The samples are read straight from the microphone, with no audio context: making one here
// waits for the computer's sound output, which froze this page for 20 s on a Mac without one.
let mic = null;   // { stream, reader, raf } while listening
async function startMic() {
  if (mic) return true;
  try {
    if (bridge && !(await bridge.media.ask('microphone'))) throw new Error('denied');
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: false } });
    if (mic || S.select !== 'sound') { stream.getTracks().forEach((t) => t.stop()); return !!mic; }   // changed meanwhile
    const reader = new MediaStreamTrackProcessor({ track: stream.getAudioTracks()[0] }).readable.getReader();
    const recent = new Float32Array(512);   // the latest 512 samples, round and round
    const listening = mic = { stream, reader, raf: 0 };
    (async () => {
      let at = 0, chunk = new Float32Array(1024);
      for (;;) {
        const { value, done } = await reader.read().catch(() => ({ done: true }));
        if (done || mic !== listening) { value?.close(); return; }
        try {
          const n = value.numberOfFrames;
          if (n > chunk.length) chunk = new Float32Array(n);
          value.copyTo(chunk, { planeIndex: 0, format: 'f32-planar' });
          for (let i = 0; i < n; i++) { recent[at] = chunk[i]; at = (at + 1) & 511; }
        } catch {} finally { value.close(); }
      }
    })();
    const tick = () => {
      if (mic !== listening) return;
      let sum = 0; for (const v of recent) sum += v * v;
      const r = onset.push(Math.sqrt(sum / recent.length), performance.now(), +S.mic);
      $('micMeter').value = r.level;
      const m = $('obMicMeter'); if (m) m.value = r.level;
      if (r.hit) onSwitch('sound');
      listening.raf = requestAnimationFrame(tick);
    };
    tick(); return true;
  } catch {
    toast(t('Microphone access is off. Allow it in System Settings › Privacy & Security › Microphone.'), 5000);
    return false;
  }
}
function stopMic() {
  if (!mic) return;
  cancelAnimationFrame(mic.raf);
  mic.reader.cancel().catch(() => {});
  mic.stream.getTracks().forEach((t) => t.stop());
  mic = null;
  $('micMeter').value = 0;
}

// ---------- targeting ----------
const isPad = (t) => t?.dataset.pad != null;
const isXY = (t) => t?.dataset.xy != null;
const isHoldable = (t) => isPad(t) || t?.dataset.nudge != null || t?.dataset.hui === 'rewind' || t?.dataset.hui === 'fastForward';
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
    if (isXY(state.current)) leaveXY(state.current);
    state.current.classList.remove('gazed'); setProgress(state.current, 0);
    if (state.fired && isHoldable(state.current) && !(S.select === 'switch' && switchDown)) release(state.current);
  }
  state.current = t; state.enteredAt = now; state.fired = false;
  if (t) { t.classList.add('gazed'); if (isPad(t) ? S.builtIn : S.tick) synth.warm(); }
}
// Each frame writes to the page only what changed: rewriting the same values 60 times a second
// kept the window redrawing (and the CPU busy) while nothing moved.
function put(el, key, value, write) {
  if (!el || el[key] === value) return;
  el[key] = value; write(value);
}
function setProgress(t, p) {
  const shown = shownProgress(p, display.reduceMotion);
  const bar = t.querySelector(':scope > .progress');
  put(bar, '_width', shown, (v) => { bar.style.width = v * 100 + '%'; });
  const fill = $('cursorFill');
  put(fill, '_dash', shown, (v) => fill.setAttribute('stroke-dasharray', `${v * 126} 126`));
}

// The frame loop runs every frame while something can change: the pointer or the head moving,
// a target settling or filling up, the camera on, calibration. Sitting still it looks 4 times a
// second: hit-testing every target 60 times a second for nothing kept the CPU busy (about 6%).
// Those looks run straight from a timer: asking for an animation frame each time woke the
// window's drawing (and the GPU process) 4 times a second, about 0.8% of the CPU on a Mac.
let framePending = false, idleTimer = 0, lastAt = '';
function wake() {
  if (framePending) return;
  framePending = true;
  requestAnimationFrame(frame);
}
function frame(now) {
  framePending = false;
  step(now);
  if (toneBusy() && !toneTimer) toneGo();
  toneDraw();
  const at = `${state.px},${state.py}`, moved = at !== lastAt;
  lastAt = at;
  const settling = state.candidate !== state.current;
  const filling = state.current && !state.fired && S.select !== 'switch';
  const toning = motion.moving || state.nudging || state.teaching;
  if (moved || settling || filling || toning || state.cameraOn || state.calibrating) wake();
  else if (!idleTimer) idleTimer = setTimeout(() => { idleTimer = 0; if (!framePending) frame(performance.now()); }, 250);
}
for (const type of ['mousemove', 'mousedown', 'keydown', 'wheel', 'resize', 'focus']) addEventListener(type, wake, { passive: true });

function step(now) {
  const cursor = $('cursor');
  // Camera modes wait for the automatic centring (about the first second) before anything can fire.
  const active = S.mode === 'mouse' || (state.cameraOn && state.autoCentre === null);
  put(cursor, '_display', active && !state.calibrating ? 'block' : 'none', (v) => { cursor.style.display = v; });
  put(cursor, '_at', `translate(${state.px}px, ${state.py}px)`, (v) => { cursor.style.transform = v; });
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
  if (isXY(t) && xyPointer(t, now)) return;
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
      ? t("I can't see your face: it's too dark. Turn on a light in front of you.")
      : t("I can't see your face. Move back into view of the camera.");
  }
  b.classList.toggle('show', !!show);
}

// ---------- switch / sound input ----------
let switchDown = false;
const IGNORE_KEYS = new Set(['Tab', 'Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Escape']);
addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || IGNORE_KEYS.has(e.key)) return;
  if (state.onboardStep === 'select' && S.select === 'switch') { markTest(t('Got it: “{key}”', { key: e.key === ' ' ? t('Space') : e.key })); }
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
// When GazeStage loses focus (say, a click into Pro Tools) the switch's key-up never arrives.
// Let go of everything momentary so no note or rewind is left stuck, and re-arm the switch.
// Notes latched with Hold stay on: the player chose those.
function releaseMomentary() {
  switchDown = false;
  if (state.heldHui) release(state.heldHui.t);
  if (state.nudging) release(state.nudging.t);
  document.querySelectorAll('#pads .target[data-down]').forEach(release);
}
addEventListener('blur', releaseMomentary);
document.addEventListener('visibilitychange', () => { if (document.hidden) releaseMomentary(); });

function onSwitch(kind) {
  if (state.onboardStep === 'select' && kind === 'sound' && S.select === 'sound') markTest(t('Heard it!'));
  if (S.select !== kind || !state.current || state.calibrating || state.settingsOpen) return;
  const target = state.current;
  if (kind === 'sound' && state.fired && isPad(target) && !S.hold) release(target);   // retrigger on each sound
  press(target, 'gaze'); state.fired = true;
}

// Mouse, touch and keyboard always work too (for helpers and for testing).
document.addEventListener('pointerdown', (e) => {
  const t = e.target.closest('.target'); if (!t || e.button !== 0) return;
  if (isXY(t)) { dragXY(t, e); return; }
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
  if (isXY(t)) {
    // A switch, sound or blink places the point where the pointer is.
    const at = xyAt(t);
    if (at && source !== 'key') placeXY(at[0], at[1]);
    return;
  }
  feedback(t);
  const d = t.dataset;
  if (d.goto) return showPage(d.goto);
  if (d.nudge) {
    nudgeXY(NUDGE[d.nudge], 0.05);
    state.nudging = { t, dir: NUDGE[d.nudge], since: performance.now() }; toneGo();
    if (source !== 'gaze' && source !== 'mouse') setTimeout(() => release(t), 250);
    return;
  }
  if (d.snap) return snapXY(d.snap);
  if (d.hui) {
    const port = HUI.PORT[d.hui];
    if (!midi.transport(port, true)) { askSuite(d.hui); return; }
    if (SUITE_TRANSPORT[d.hui]) bridge?.suite?.did(d.hui);
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
  if (state.nudging && state.nudging.t === t) state.nudging = null;
}

// ---------- Limitless Sound ----------
// Other suite apps (Voice, the controller, a Stream Deck) can drive GazeStage, and when
// Pro Tools isn't linked, GazeStage's transport asks whichever suite app can do it.
const SUITE_TRANSPORT = { play: () => t('Playing'), stop: () => t('Stopped'), record: () => t('Recording') };
const SUITE_DO = {
  pads: () => showPage('play'), transport: () => showPage('transport'),
  octaveUp: () => action('octup'), octaveDown: () => action('octdown'), scale: () => action('scale'),
  latch: () => action('hold'), panic: () => action('panic'),
  tone: () => showPage('tone'),
  'xySet': (a) => {
    // x and y are 0..1, or 0..127 like a MIDI value. A missing axis stays where it is.
    const v = (n, cur) => (n == null || n === '' || !Number.isFinite(+n) ? cur : +n > 1 ? +n / 127 : +n);
    placeXY(v(a.x, motion.x), v(a.y, motion.y), a.glide != null && Number.isFinite(+a.glide) ? +a.glide : undefined);
    return `${xyName('X')} ${toCC(motion.glide?.x ?? motion.x)}, ${xyName('Y')} ${toCC(motion.glide?.y ?? motion.y)}`;
  },
  'xySnapA': () => snapXY('A'), 'xySnapB': () => snapXY('B'), 'xySnapC': () => snapXY('C'), 'xySnapD': () => snapXY('D'),
  'xyCenter': () => action('xyCenter'),
  'xyLeft': () => nudgeXY(NUDGE.left, 0.1), 'xyRight': () => nudgeXY(NUDGE.right, 0.1),
  'xyUp': () => nudgeXY(NUDGE.up, 0.1), 'xyDown': () => nudgeXY(NUDGE.down, 0.1),
  'xyFollow': () => { action('xyFollow'); return S.xyFollow ? t('Follow on') : t('Follow off'); },
};
let suiteOn = false;

function suiteInvoke(name, args = {}) {
  if (SUITE_TRANSPORT[name]) {
    const port = HUI.PORT[name];
    if (!midi.transport(port, true)) return { ok: false, message: t('GazeStage isn’t linked to Pro Tools.') };
    setTimeout(() => midi.transport(port, false), 90);
    // The flash and click come after the answer has gone back.
    const target = document.querySelector(`[data-hui="${name}"]`);
    if (target) setTimeout(() => feedback(target));
    return { ok: true, message: SUITE_TRANSPORT[name]() };
  }
  const run = SUITE_DO[name];
  if (!run) return { ok: false, message: t('GazeStage has no action “{name}”.', { name }) };
  const said = run(args && typeof args === 'object' ? args : {});
  return { ok: true, message: typeof said === 'string' ? said : '' };
}

async function askSuite(hui) {
  const notLinked = t('Not connected to Pro Tools yet. See Settings › Pro Tools and MIDI.');
  if (!SUITE_TRANSPORT[hui] || !suiteOn) return toast(notLinked, 4000);
  const r = await bridge.suite.invoke(`daw.${hui}`);
  toast(r.ok ? (r.message || SUITE_TRANSPORT[hui]()) : notLinked, r.ok ? 1800 : 4000);
}

bridge?.suite?.onInvoke(({ id, action: name, args }) => {
  let result;
  try { result = suiteInvoke(String(name), args); } catch (e) { result = { ok: false, message: String(e?.message || e) }; }
  bridge.suite.reply(id, result);
});
bridge?.suite?.onConnected((on) => { suiteOn = !!on; if (!on && shared) { shared = null; applyDisplay(); } });
bridge?.suite?.status().then((s) => { suiteOn = !!s?.connected; if (s?.prefs) useShared(s.prefs); });

// The musician's shared settings, from the hub's welcome and every change after it.
function useShared(prefs) { shared = prefs || {}; reported = ''; applyDisplay(); }
bridge?.suite?.onPrefs(useShared);
// Once they're on screen, tell the hub what's in use: only the settings GazeStage honors, and its language.
function reportDisplay() {
  if (!shared) return;
  const applied = { textScale: Math.round(display.textScale * 100) / 100, highContrast: display.highContrast, reduceMotion: display.reduceMotion, language: lang };
  if (JSON.stringify(applied) === reported) return;
  reported = JSON.stringify(applied); bridge.suite.applied(applied);
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
    case 'panic': allNotesOff(); toast(t('All notes off')); return;
    case 'xyStore': state.xyStore = !state.xyStore; clearTimeout(state.xyStoreTimer);
      if (state.xyStore) state.xyStoreTimer = setTimeout(() => { state.xyStore = false; renderTone(); }, 12000);
      return renderTone();
    case 'xyFollow': S.xyFollow = !S.xyFollow; save(); state.xyAnchor = null; return renderTone();
    case 'xyGlide': { const i = GLIDES.indexOf(+S.xyGlide); S.xyGlide = GLIDES[(i + 1) % GLIDES.length]; save(); return renderTone(); }
    case 'xyCenter': return placeXY(0.5, 0.5);
    case 'xyListen': return listen(!state.listen);
  }
  save(); if (a !== 'hold' && a !== 'sound') allNotesOff();
  renderInstrument(); syncSettingsForm();
}

function setPaused(p) {
  state.paused = p; $('pauseOverlay').classList.toggle('show', p);
  if (p) { allNotesOff(); listen(false); if (state.heldHui) release(state.heldHui.t); state.nudging = null; motion.chase = null; }
  toast(p ? t('Paused. Look at Resume to continue.') : t('Resumed'));
}

function showPage(id) {
  // Notes latched with Hold keep sounding (play a chord, then shape it on the tone pad).
  if (S.hold) document.querySelectorAll('#pads .target[data-down]').forEach(release); else allNotesOff();
  if (id !== 'tone') listen(false);
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
      b.setAttribute('aria-label', t('Play {note}', { note: padLabel(p) }));
      b.innerHTML = `${padLabel(p)}<small>${p.sub === 'root' ? t('root') : p.sub || '&nbsp;'}</small><span class="progress"></span>`;
      grid.appendChild(b);
    }
  $('octLabel').textContent = NOTE_NAMES[+S.key] + S.octave;
  $('scaleLabel').textContent = `${NOTE_NAMES[+S.key]} ${t(S.scale)}`;
  $('chordsLabel').textContent = S.chords ? t('on') : t('off');
  $('holdLabel').textContent = S.hold ? t('on') : t('off');
  $('soundLabel').textContent = S.builtIn ? t(SYNTH_PRESETS[S.preset]) : t('MIDI only');
  document.querySelector('[data-action=chords]').setAttribute('aria-pressed', S.chords);
  document.querySelector('[data-action=hold]').setAttribute('aria-pressed', S.hold);
}
// A pad's name: a note, or a chord (lib.js names one it has no symbol for "<note> chord").
const padLabel = (p) => (p.label.endsWith(' chord') ? t('{note} chord', { note: p.label.slice(0, -6) }) : p.label);
function addProgressBars(root = document) {
  root.querySelectorAll('.target').forEach(t => { if (!t.querySelector(':scope > .progress')) t.insertAdjacentHTML('beforeend', '<span class="progress"></span>'); });
}

// ---------- tone pad ----------
// One point, two MIDI controllers: left–right and down–up. Made for shifting an amp or a
// plugin hands-free: a Line 6 Helix (EXP 1 and 2), or anything with MIDI learn.
//   Place (default): look somewhere on the pad and hold still, and the point glides there.
//                    A switch, sound or blink places it at the pointer straight away.
//   Follow:          the point follows the pointer while it is on the pad (after a short
//                    settle, so looking across the pad doesn't sweep the tone). With a switch,
//                    it follows only while the switch is held.
//   Arrows step it (keep looking to keep moving), A–D recall saved tones, Glide sets how
//   long a move takes.
const NUDGE = { left: [-1, 0], right: [1, 0], up: [0, 1], down: [0, -1] };
const GLIDES = [0, 250, 500, 1000, 2000, 4000];
const XY_STILL_PX = 40;
const xyCC = () => {
  const p = XY_PROFILES[S.xyProfile] || XY_PROFILES.learn;
  return S.xyProfile === 'custom' ? [+S.xyCcX & 127, +S.xyCcY & 127] : [p.x, p.y];
};
const glideText = (ms) => (+ms === 0 ? t('instant') : `${(+ms / 1000).toFixed(+ms < 1000 ? 2 : 0).replace(/0$/, '')} s`);
// The axis names: the musician's own, or GazeStage's in its language.
const xyName = (axis) => { const v = S['xyName' + axis]; return v === DEFAULTS['xyName' + axis] ? t(v) : v; };

// The pad position (0..1, y up) under the pointer, or null when the pointer is off the pad.
function xyAt(t, px = state.px, py = state.py) {
  const r = t.getBoundingClientRect();
  if (px < r.left || px > r.right || py < r.top || py > r.bottom) return null;
  return [clamp((px - r.left) / r.width, 0, 1), clamp(1 - (py - r.top) / r.height, 0, 1)];
}
function showAim(at) {
  const a = $('xyAim'); a.classList.toggle('show', !!at);
  if (at) { a.style.left = at[0] * 100 + '%'; a.style.top = (1 - at[1]) * 100 + '%'; }
}
function leaveXY(t) {
  showAim(null); t.classList.remove('following'); state.xyAnchor = null;
}

// Runs every frame while the pointer is on the pad. true when it handled selection itself.
function xyPointer(t, now) {
  const at = xyAt(t);
  showAim(at);
  if (S.xyFollow) {
    setProgress(t, 0);
    const steer = at && (S.select === 'switch' ? switchDown : now - state.enteredAt >= 300);
    t.classList.toggle('following', !!steer);
    if (steer) motion.chaseTo(at[0], at[1], 90);
    return true;
  }
  // Placing means "hold still here": moving to a new spot restarts the dwell ring and re-arms
  // a long blink, so the point can be placed again without leaving the pad.
  const a = state.xyAnchor;
  if (!a || Math.hypot(state.px - a.x, state.py - a.y) > XY_STILL_PX) {
    state.xyAnchor = { x: state.px, y: state.py }; state.enteredAt = now; state.fired = false;
  }
  if (S.select !== 'dwell') return false;   // switch, sound and blink go through press()
  if (!at || state.fired) { setProgress(t, 0); return true; }
  const p = (now - state.enteredAt) / Math.max(400, +S.dwell * 0.7);
  setProgress(t, p);
  if (p >= 1) { placeXY(at[0], at[1]); state.fired = true; setProgress(t, 0); }
  return true;
}

function placeXY(x, y, ms = +S.xyGlide) { motion.glideTo(x, y, ms, performance.now()); toneGo(); wake(); }
function nudgeXY([dx, dy], step) {
  const x = motion.glide ? motion.glide.x : motion.x, y = motion.glide ? motion.glide.y : motion.y;
  motion.glideTo(clamp(x + dx * step, 0, 1), clamp(y + dy * step, 0, 1), 120, performance.now());
  toneGo(); wake();
}
function snapXY(k) {
  if (state.xyStore) {
    S.xySnaps = { ...S.xySnaps, [k]: [motion.x, motion.y] }; save();
    state.xyStore = false; clearTimeout(state.xyStoreTimer);
    renderTone(); toast(t('Saved this tone to {letter}', { letter: k }));
    return t('Saved to {letter}', { letter: k });
  }
  const p = S.xySnaps[k]; if (!p) return;
  placeXY(p[0], p[1]);
  const b = document.querySelector(`[data-snap="${k}"]`); if (b && state.page === 'tone') feedback(b);
  return t('Tone {letter}', { letter: k });
}
// Mouse, touch or a helper: press and drag on the pad.
function dragXY(t, e) {
  if (state.paused) return;
  if (state.current === t) state.fired = true;
  const go = (ev, instant) => {
    const r = t.getBoundingClientRect();
    const x = clamp((ev.clientX - r.left) / r.width, 0, 1), y = clamp(1 - (ev.clientY - r.top) / r.height, 0, 1);
    if (instant) placeXY(x, y, Math.min(+S.xyGlide, 150)); else { motion.chaseTo(x, y, 40); toneGo(); wake(); }
  };
  go(e, true);
  try { t.setPointerCapture(e.pointerId); } catch {}
  const move = (ev) => go(ev, false);
  const up = () => { t.removeEventListener('pointermove', move); t.removeEventListener('pointerup', up); t.removeEventListener('pointercancel', up); };
  t.addEventListener('pointermove', move); t.addEventListener('pointerup', up); t.addEventListener('pointercancel', up);
}
$('xy').addEventListener('keydown', (e) => {
  const dir = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }[e.key];
  if (!dir) return;
  e.preventDefault(); e.stopPropagation();
  nudgeXY(NUDGE[dir], e.shiftKey ? 0.01 : 0.05);
});

// The point moves and its MIDI goes out on a timer of its own, every 10 ms while it moves, not
// with the drawing: frames stop while GazeStage is minimised and slow down behind other windows,
// and "tone A" from Voice has to reach the Helix with Pro Tools in front. toneDraw() shows it.
let lastDrawn = '', xySaveDue = false, toneTimer = 0;
const toneBusy = () => motion.moving || !!state.nudging || !!state.teaching;
function toneGo() {
  toneStep(performance.now());   // a placement goes out at once
  if (toneTimer || !toneBusy()) return;
  toneTimer = setInterval(() => {
    toneStep(performance.now());
    if (!toneBusy()) { clearInterval(toneTimer); toneTimer = 0; }
  }, 10);
}
function toneStep(now) {
  const n = state.nudging;
  if (n && now - n.since > 350 && !state.paused) {
    // Held arrow: keep moving, the full width in about three seconds.
    const dt = Math.min(50, now - (n.last || now)); n.last = now;
    motion.stop();
    motion.x = clamp(motion.x + n.dir[0] * dt / 3000, 0, 1); motion.y = clamp(motion.y + n.dir[1] * dt / 3000, 0, 1);
  }
  const [x, y] = motion.step(now);
  const [ccX, ccY] = xyCC();
  if (state.teaching) {
    // MIDI learn helper: sweep only one controller down, up and back.
    const k = state.teaching, p = (now - k.t0) / 1500, cur = k.axis === 'x' ? x : y;
    const v = p >= 1 ? cur : p < 0.33 ? cur * (1 - p / 0.33) : p < 0.66 ? (p - 0.33) / 0.33 : 1 - (1 - cur) * (p - 0.66) / 0.34;
    midi.sendTone([0xb0 | ((+S.xyChannel - 1) & 15), k.axis === 'x' ? ccX : ccY, toCC(v)]);
    if (p >= 1) { state.teaching = null; state.xySent = { ...state.xySent, [k.axis]: toCC(cur) }; }
    return;
  }
  const r = xyMessages(+S.xyChannel, ccX, ccY, x, y, state.xySent);
  if (r.bytes.length) {
    midi.sendTone(r.bytes); state.xySent = r.sent;
    if (S.xyShape) synth.shape(x, y);
    xySaveDue = true;
  }
  if (xySaveDue && !motion.moving && !state.nudging) { S.xyX = x; S.xyY = y; save(); xySaveDue = false; }
}
// With the frames: the point where it is now, and only when that changed.
function toneDraw() {
  const x = motion.x, y = motion.y, cx = toCC(x), cy = toCC(y);
  const key = `${x.toFixed(4)},${y.toFixed(4)}`;
  if (key === lastDrawn) return;
  lastDrawn = key;
  const puck = $('xyPuck'); puck.style.left = x * 100 + '%'; puck.style.top = (1 - y) * 100 + '%';
  const text = `${xyName('X')} ${cx} · ${xyName('Y')} ${cy}`;
  $('xyReadout').textContent = text; $('xy').setAttribute('aria-valuetext', text);
  for (const b of document.querySelectorAll('[data-snap]')) {
    const p = S.xySnaps[b.dataset.snap];
    b.classList.toggle('lit', !!p && Math.abs(p[0] - x) < 0.02 && Math.abs(p[1] - y) < 0.02);
  }
}

// Drawn again only when something it shows has changed: the output is looked for every 4 s
// (a Helix plugged in), and redrawing the same page each time kept the window busy.
let toneShown = '';
function renderTone() {
  const shows = JSON.stringify([lang, S.xyNameX, S.xyNameY, S.xySnaps, state.xyStore, S.xyFollow, S.select, S.xyGlide,
    !!state.listen, xyCC(), S.xyChannel, S.xyProfile, midi.toneName, midi.toneMissing]);
  if (shows === toneShown) return;
  toneShown = shows;
  $('xyNameX').textContent = xyName('X'); $('xyNameY').textContent = xyName('Y');
  for (const m of document.querySelectorAll('.snapmark')) {
    const p = S.xySnaps[m.dataset.mark];
    m.style.display = p ? '' : 'none';
    if (p) { m.style.left = p[0] * 100 + '%'; m.style.top = (1 - p[1]) * 100 + '%'; }
  }
  const store = document.querySelector('[data-action=xyStore]');
  store.setAttribute('aria-pressed', state.xyStore);
  $('xyStoreLabel').textContent = state.xyStore ? t('now pick A, B, C or D') : t('then pick A–D');
  document.querySelectorAll('[data-snap]').forEach(b => b.classList.toggle('armed', state.xyStore));
  document.querySelector('[data-action=xyFollow]').setAttribute('aria-pressed', S.xyFollow);
  $('xyFollowLabel').textContent = S.xyFollow
    ? (S.select === 'switch' ? t('on: hold the switch to steer') : t('on: the point follows you'))
    : t('off: look and hold to place');
  $('xyGlideLabel').textContent = glideText(S.xyGlide);
  document.querySelector('[data-action=xyListen]').setAttribute('aria-pressed', !!state.listen);
  const [ccX, ccY] = xyCC();
  const to = midi.toneName ? `<b>${esc(midi.toneName)}</b>` : t('nothing yet (choose an output in Settings)');
  $('xyHint').innerHTML = t('{x} sends CC {ccX} and {y} sends CC {ccY} on channel {channel}, to {to}.', { x: esc(xyName('X')), ccX, y: esc(xyName('Y')), ccY, channel: S.xyChannel, to }) + ' '
    + (midi.toneMissing ? t("{name} isn't connected.", { name: `<b>${esc(midi.toneMissing)}</b>` }) + ' ' : '')
    + (S.xyProfile === 'helix' ? t('On the Helix, assign the controls you want to EXP 1 and EXP 2.') : t('Use MIDI learn on the controls you want, with Settings › Tone pad › Teach.'))
    + ` <button class="linkish" data-cmd="settings">${t('Tone pad settings')}</button>`;
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// Listen: hold a chord on the built-in sound (not sent over MIDI) to hear the pad shape it.
function listen(on) {
  if (!on === !state.listen) return;
  if (on) {
    if (!S.xyShape) { S.xyShape = true; save(); syncSettingsForm(); }
    synth.warm(); synth.shape(motion.x, motion.y);
    state.listen = buildPads({ key: +S.key, octave: 3, scale: S.scale, count: 1, chords: true })[0].notes;
    state.listen.forEach(n => synth.noteOn(n, 90));
  } else {
    state.listen.forEach(n => synth.noteOff(n)); state.listen = null;
  }
  renderTone();
}

// Which output the pad sends to; checked again as devices come and go.
let toneFound = null;
async function refreshToneOut() {
  if (midi.mode === 'none') return;
  const before = midi.toneName;
  await midi.resolveTone(S.xyOut);
  if (S.xyOut === 'auto' && midi.toneName !== before && midi.toneName !== midi.nativePorts?.notes && midi.toneName && midi.toneName !== toneFound) {
    toneFound = midi.toneName; toast(t('Found {name}. The tone pad sends to it.', { name: midi.toneName }), 4000);
  }
  renderTone();
  if (state.settingsOpen) renderToneSettings();
}
setInterval(refreshToneOut, 4000);

async function renderToneSettings() {
  const sel = $('sToneOut'), list = await midi.toneOutputs();
  const notes = midi.mode === 'native' ? t('GazeStage Notes (Pro Tools tracks and plugins)') : t('The instrument output');
  sel.innerHTML = '';
  sel.add(new Option(t('Automatic'), 'auto'));
  sel.add(new Option(notes, 'notes'));
  list.forEach(p => sel.add(new Option(p.name, p.id)));
  if (![...sel.options].some(o => o.value === S.xyOut)) sel.add(new Option(t('{name} (not connected)', { name: S.xyOut }), S.xyOut));
  sel.value = S.xyOut;
  $('sToneOutHelp').textContent = (S.xyOut === 'auto' ? t('Automatic sends to a Line 6 Helix, HX or POD Go when one is plugged in over USB, and otherwise to GazeStage Notes.') + ' ' : '')
    + (midi.toneName ? t('Sending to {name} now.', { name: midi.toneName }) : t('Nothing to send to yet.'));
  $('xyCustomRow').style.display = S.xyProfile === 'custom' ? '' : 'none';
}
for (let c = 1; c <= 16; c++) $('sXyChannel').add(new Option(String(c), c));
$('xyTeachX').onclick = () => { state.teaching = { axis: 'x', t0: performance.now() }; toneGo(); wake(); toast(t('Sending only {name} (CC {cc})', { name: xyName('X'), cc: xyCC()[0] })); };
$('xyTeachY').onclick = () => { state.teaching = { axis: 'y', t0: performance.now() }; toneGo(); wake(); toast(t('Sending only {name} (CC {cc})', { name: xyName('Y'), cc: xyCC()[1] })); };

// ---------- Pro Tools LEDs ----------
const leds = { play: false, record: false };
midi.addEventListener('led', (e) => {
  const { zone, port, on } = e.detail;
  if (zone !== HUI.TRANSPORT_ZONE) return;
  if (port === HUI.PORT.play) leds.play = on;
  else if (port === HUI.PORT.record) leds.record = on;
  else return;
  renderLeds();
});
function renderLeds() {
  $('tPlay').classList.toggle('lit', leds.play); $('tPlayState').textContent = leds.play ? t('playing') : t('Pro Tools play');
  $('tRec').classList.toggle('lit', leds.record); $('tRecState').textContent = leds.record ? t('record armed') : t('record arm the transport');
}
midi.addEventListener('change', () => { refreshChips(); renderMidiSettings(); refreshToneOut(); });

// ---------- what the keyboard can reach ----------
// Only the top layer on screen takes keyboard focus. The guided setup and calibration cover the
// whole window, the open settings drawer its right side, the pause screen the page, and the closed
// drawer waits off screen: without this, Tab walked into controls nobody could see, and a screen
// reader read them. The face banner floats above the page and the drawer, so it stays readable.
const LAYERS = [['pauseOverlay', 'show'], ['settings', 'open'], ['onboard', 'show'], ['calib', 'show']];   // bottom to top
const pageParts = [document.querySelector('.topbar'), ...document.querySelectorAll('main > :not(.banner)')];
function syncLayers() {
  const top = LAYERS.findLastIndex(([id, cls]) => $(id).classList.contains(cls));
  const inert = (el, on) => { if (el.inert !== on) el.inert = on; };
  for (const el of pageParts) inert(el, top >= 0);
  LAYERS.forEach(([id, cls], i) => inert($(id), i < top || !$(id).classList.contains(cls)));
}
const layerWatch = new MutationObserver(syncLayers);
for (const [id] of LAYERS) layerWatch.observe($(id), { attributes: true, attributeFilter: ['class'] });
syncLayers();

// ---------- settings drawer ----------
function openSettings() {
  state.settingsOpen = true; syncSettingsForm(); renderMidiSettings(); renderToneSettings(); refreshCalInfo();
  $('settings').classList.add('open'); $('settings').setAttribute('aria-hidden', 'false');
  syncLayers(); $('closeSettings').focus();
  if (S.select === 'sound') startMic();
}
function closeSettings() {
  const hadFocus = $('settings').contains(document.activeElement);
  state.settingsOpen = false; $('settings').classList.remove('open'); $('settings').setAttribute('aria-hidden', 'true');
  syncLayers();
  if (hadFocus) $('settingsBtn').focus();   // back to where it was opened
}
$('settingsBtn').onclick = openSettings; $('closeSettings').onclick = closeSettings;
$('recenterBtn').onclick = recenter; $('calibBtn').onclick = calibrate;
addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.settingsOpen) closeSettings(); });

const FORM = {
  sMode: 'mode', sRange: 'range', sSmooth: 'smooth', sCamera: 'camera', sPreview: 'preview',
  sSelect: 'select', sDwell: 'dwell', sPadDwell: 'padDwell', sBlink: 'blink', sMic: 'mic', sTick: 'tick',
  sBuiltIn: 'builtIn', sPreset: 'preset', sVolume: 'volume', sKey: 'key', sScale: 'scale', sPads: 'pads', sVelocity: 'velocity',
  sTheme: 'theme', sContrast: 'contrast', sSize: 'size', sSpacing: 'spacing', sOnTop: 'onTop',
  sToneOut: 'xyOut', sXyProfile: 'xyProfile', sXyCcX: 'xyCcX', sXyCcY: 'xyCcY', sXyChannel: 'xyChannel',
  sXyNameX: 'xyNameX', sXyNameY: 'xyNameY', sXyShape: 'xyShape',
};
NOTE_NAMES.forEach((n, i) => $('sKey').add(new Option(n, i)));
// The pick lists with names in GazeStage's language, filled again when it changes.
function fillOptions() {
  const fill = (id, items) => { const sel = $(id), was = sel.value; sel.length = 0; for (const [value, text] of items) sel.add(new Option(text, value)); sel.value = was; };
  fill('sXyProfile', Object.entries(XY_PROFILES).map(([k, v]) => [k, v.x != null ? t('{name} (CC {x} and {y})', { name: t(v.name), x: v.x, y: v.y }) : t(v.name)]));
  fill('sPreset', Object.entries(SYNTH_PRESETS).map(([k, v]) => [k, t(v)]));
  fill('sScale', Object.keys(SCALES).map((n) => [n, t(n)]));
}
fillOptions();
function syncSettingsForm() {
  for (const [id, key] of Object.entries(FORM)) {
    const el = $(id); if (el.type === 'checkbox') el.checked = !!S[key]; else el.value = S[key];
  }
  $('sXyNameX').value = xyName('X'); $('sXyNameY').value = xyName('Y');
  $('sDwellOut').textContent = (S.dwell / 1000).toFixed(2) + ' s';
  $('sPadDwellOut').textContent = +S.padDwell === 0 ? t('instant') : (S.padDwell / 1000).toFixed(2) + ' s';
  $('sBlinkOut').textContent = (S.blink / 1000).toFixed(2) + ' s';
  $('sModeHelp').textContent = {
    head: t('Turn your head to move. Works right away; Recenter if it drifts.'),
    eyes: t('Look where you want to go. Needs calibration and a steady head.'),
    mouse: t('Use a mouse, trackpad, joystick, head mouse or the macOS Head Pointer, with dwell or a switch to select.'),
  }[S.mode];
}
for (const [id, key] of Object.entries(FORM)) {
  const el = $(id);
  const handler = () => {
    let v = el.type === 'checkbox' ? el.checked : el.type === 'range' ? +el.value : el.value;
    if (el.type === 'number') v = clamp(Math.round(+v) || 0, +el.min, +el.max);
    if (el.type === 'text') v = v.trim() === t(DEFAULTS[key]) ? DEFAULTS[key] : v.trim() || DEFAULTS[key];   // a name as shown is GazeStage's own
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
    case 'select': if (S.select === 'sound') await startMic(); else stopMic(); if (S.select === 'blink' && !state.cameraOn) await startCamera(); break;
    case 'builtIn': if (!S.builtIn) synth.allOff(); renderInstrument(); break;
    case 'preset': synth.setPreset(S.preset); renderInstrument(); break;
    case 'volume': synth.setVolume(+S.volume); break;
    case 'key': case 'scale': case 'pads': allNotesOff(); renderInstrument(); break;
    case 'xyOut': await refreshToneOut(); break;
    case 'xyProfile': case 'xyCcX': case 'xyCcY': case 'xyChannel':
      state.xySent = {}; toneGo(); renderTone(); renderToneSettings(); break;   // resend on the new controllers
    case 'xyNameX': case 'xyNameY': lastDrawn = ''; renderTone(); break;
    case 'xyShape': if (S.xyShape) synth.shape(motion.x, motion.y); else { synth.shape(null); listen(false); } break;
  }
  applyDisplay(); refreshChips();
}
$('clearCal').onclick = () => { S.cal = { ...S.cal, [S.mode]: undefined }; delete S.cal[S.mode]; save(); state.offset = { x: 0, y: 0 }; refreshCalInfo(); toast(t('Calibration cleared')); };
$('resetAll').onclick = async () => {
  // Asked by the main process: a confirm() here would stop this page answering other apps until someone answers it.
  const question = t('Reset every GazeStage setting, including calibration?');
  if (!(bridge ? await bridge.confirm(question, t('Reset')) : confirm(question))) return;
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
  fill('sOutHui', 'huiOut', t('Not connected')); fill('sInHui', 'huiIn', t('Not connected')); fill('sOutNotes', 'notes', t('Not connected'));
  const win = bridge?.platform === 'win32' || /Windows/.test(navigator.userAgent);
  $('midiWebSteps').innerHTML = (win
    ? [t('Open <b>MIDI Settings</b> (Windows 11) or install the free <b>loopMIDI</b>.'), t('Create three ports: <code>To Pro Tools</code>, <code>From Pro Tools</code> and <code>GazeStage Notes</code>.')]
    : [t('Open <b>Audio MIDI Setup</b>, choose Window › Show MIDI Studio, and turn on the <b>IAC Driver</b>.'), t('Add three ports: <code>To Pro Tools</code>, <code>From Pro Tools</code> and <code>GazeStage Notes</code>.')])
    .concat([t('GazeStage picks them up by name. In Pro Tools, add a <b>HUI</b> receiving from <code>To Pro Tools</code> and sending to <code>From Pro Tools</code>.')])
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
    case 'page:tone': return showPage('tone');
    case 'panic': return allNotesOff();
    case 'onboarding': closeSettings(); return startOnboarding();
    case 'toggle-on-top': S.onTop = !S.onTop; save(); applyDisplay(); return toast(S.onTop ? t('GazeStage stays on top') : t('GazeStage no longer stays on top'));
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
  return `<div class="actions">${back ? `<button class="target" data-ob="back">${t('Back')}</button>` : '<span></span>'}${extra}<button class="target primary" data-ob="${nextOb}">${nextLabel}</button></div>`;
}

function renderStep(step) {
  const again = state.onboardStep === step;   // the same step again, say in a new language
  state.onboardStep = step;
  const card = $('onboardCard');
  let html = stepper(step);
  if (step === 'welcome') {
    html += `<h1>${t('Welcome to GazeStage')}</h1>
      <p class="lead">${t('Play music and run Pro Tools with your head, your eyes, a sound or a switch. This takes about two minutes. Everything stays on this computer: nothing is recorded or sent anywhere.')}</p>
      <div class="note">${t('A helper can click through these steps with a mouse. Once the camera is on, you can also select everything here by looking at it and holding still.')}</div>
      <div class="actions"><button class="target" data-ob="skip">${t('Skip setup')}</button><button class="target primary" data-ob="next">${t('Get started')}</button></div>`;
  } else if (step === 'camera') {
    html += `<h2>${t('Turn on the camera')}</h2>
      <p class="lead">${t("GazeStage follows your head and eyes with the camera. Sit about an arm's length from the screen with your face in the oval.")}</p>
      <div class="camstage"><div class="bigcam"><video data-mirror playsinline muted></video><div class="guide" id="obGuide"></div></div>
      <ul class="checks">
        <li id="ckFace"><span class="dot"></span><span>${t('Face found')}<small>${t('Look toward the screen.')}</small></span></li>
        <li id="ckLight"><span class="dot"></span><span>${t('Enough light')}<small>${t('Light in front of you works best, not a bright window behind.')}</small></span></li>
        <li id="ckCentre"><span class="dot"></span><span>${t('Centred')}<small>${t('Keep your face in the middle of the picture.')}</small></span></li>
        <li id="ckDist"><span class="dot"></span><span>${t('Good distance')}<small>${t("About an arm's length away.")}</small></span></li>
      </ul></div>
      <p id="camMsg" class="lead" style="margin:0 0 12px"></p>
      ${actions(true, state.cameraOn ? t('Continue') : t('Turn on camera'), state.cameraOn ? 'next' : 'camera', `<button class="target" data-ob="nocam">${t('Use a mouse instead')}</button>`)}`;
  } else if (step === 'pointer') {
    html += `<h2>${t('How do you want to point?')}</h2><p class="lead">${t('You can change this any time in Settings.')}</p>
      <div class="choices">
        ${choice('mode', 'head', t('My head'), t('Turn your head a little to move. Steady and works right away.'), S.mode === 'head', t('Recommended'))}
        ${choice('mode', 'eyes', t('My eyes'), t('Look where you want to go. Needs a short calibration and a still head.'), S.mode === 'eyes')}
        ${choice('mode', 'mouse', t('Mouse or another pointer'), t('Mouse, trackpad, joystick, head mouse or the macOS Head Pointer.'), S.mode === 'mouse')}
      </div>
      <div class="row" style="max-width:520px"><label for="obRange">${t('Head movement needed')}</label><select id="obRange"><option value="10">${t('Small')}</option><option value="16">${t('Medium')}</option><option value="24">${t('Large')}</option></select></div>
      ${actions(true, t('Continue'))}`;
  } else if (step === 'select') {
    html += `<h2>${t('How do you want to select?')}</h2><p class="lead">${t('Point at something, then select it one of these ways.')}</p>
      <div class="choices">
        ${choice('select', 'dwell', t('Look and hold'), t('Keep pointing at it for a moment. Nothing else needed.'), S.select === 'dwell', t('Recommended'))}
        ${choice('select', 'switch', t('Switch or key'), t('Any key, adaptive switch, foot pedal or Xbox Adaptive Controller button.'), S.select === 'switch')}
        ${choice('select', 'sound', t('A short sound'), t('A pop, click or “ta” into the microphone. Great for rhythm.'), S.select === 'sound')}
        ${choice('select', 'blink', t('A long blink'), t('Close both eyes a little longer than a normal blink.'), S.select === 'blink')}
      </div>
      <div class="note" id="obTest">${selectTestText()}</div>
      ${actions(true, t('Continue'))}`;
  } else if (step === 'practice') {
    if (!again) state.practiceDone = new Set();
    const how = { dwell: t('Point at one and hold still until the ring fills.'), switch: t('Point at one and press your switch.'),
      sound: t('Point at one and make your sound.'), blink: t('Point at one and close your eyes for a moment.') }[S.select];
    html += `<h2>${t('Try it')}</h2><p class="lead">${t('Select each of the three targets.')} ${how}</p>
      <div class="practice"><button class="target" data-practice="1">${t('One')}</button><button class="target" data-practice="2">${t('Two')}</button><button class="target" data-practice="3">${t('Three')}</button></div>
      <p id="practiceMsg" class="lead" style="margin:0 0 12px"></p>
      ${actions(true, t('Continue'), 'next', S.mode !== 'mouse' ? `<button class="target" data-ob="recenter">${t('Recenter')}</button><button class="target" data-ob="calibrate">${S.mode === 'eyes' ? t('Calibrate') : t('Calibrate (optional)')}</button>` : '')}`;
  } else if (step === 'done') {
    const native = midi.mode === 'native';
    html += `<h2>${t("You're ready")}</h2>
      <p class="lead">${t('Play the built-in instrument straight away. To control Pro Tools, connect it once:')}</p>
      <div class="note">${native
        ? `<ol class="steps" style="color:inherit"><li>${t('In Pro Tools choose <b>Setup › Peripherals › MIDI Controllers</b>.')}</li><li>${t('Add a <b>HUI</b> with Receive From and Send To set to <code>GazeStage HUI</code>.')}</li><li>${t("For instruments, set an instrument track's input to <code>GazeStage Notes</code>.")}</li></ol>`
        : t('Open Settings › Pro Tools and MIDI to choose your loopback ports.')}</div>
      <div class="actions"><button class="target" data-ob="finish-transport">${t('Go to Transport')}</button><button class="target primary" data-ob="finish-play">${t('Start playing')}</button></div>`;
  }
  card.innerHTML = html;
  addProgressBars(card);
  if (step === 'practice' && again && state.practiceDone.size) {
    for (const n of state.practiceDone) card.querySelector(`[data-practice="${n}"]`)?.classList.add('done');
    renderPracticeState();
  }
  if (step === 'camera') { for (const v of card.querySelectorAll('video[data-mirror]')) { v.srcObject = tracker.stream || null; v.play?.().catch(() => {}); } }
  if (step === 'pointer') { const r = $('obRange'); r.value = S.range; r.onchange = () => { S.range = r.value; save(); }; }
  if (step === 'select' && S.select === 'sound') startMic();
}

function selectTestText() {
  return {
    dwell: t('Tip: you can change how long to hold in Settings.'),
    switch: t('Press your switch or any key now to test it.'),
    sound: `${t('Make a short pop or click sound now to test it.')} <meter id="obMicMeter" min="0" max="1" value="0" style="width:160px;vertical-align:middle"></meter>`,
    blink: t('Close both eyes a little longer than a normal blink to test it.'),
  }[S.select];
}
function markTest(text) { const el = $('obTest'); if (el) el.innerHTML = `<b style="color:var(--ok)">✓ ${text}</b>`; }
function renderPracticeState() {
  const m = $('practiceMsg'); if (!m) return;
  m.innerHTML = state.practiceDone.size >= 3 ? `<b style="color:var(--ok)">${t('✓ Nicely done.')}</b>` : t('{done} of 3', { done: state.practiceDone.size });
}

function updateOnboardChecks(s) {
  if (state.onboardStep !== 'camera') return;
  const set = (id, ok) => { const d = $(id)?.querySelector('.dot'); if (d) d.className = 'dot ' + (ok == null ? '' : ok ? 'ok' : 'warn'); };
  set('ckFace', s.face); set('ckLight', s.brightness > 0.2);
  set('ckCentre', s.face ? s.offCentre < 0.4 : null); set('ckDist', s.face ? s.size > 0.16 && s.size < 0.62 : null);
  const good = s.face && s.brightness > 0.2 && s.offCentre < 0.4 && s.size > 0.16 && s.size < 0.62;
  $('obGuide')?.classList.toggle('ok', !!good);
}

async function onboardAction(ob, target) {
  const step = state.onboardStep, i = STEPS.indexOf(step);
  if (ob === 'skip') return finishOnboarding('transport');
  if (ob === 'back') return renderStep(STEPS[Math.max(0, i - 1)]);
  if (ob === 'camera') {
    $('camMsg').textContent = t('Starting the camera…');
    const ok = await startCamera();
    if (ok) return renderStep('camera');
    $('camMsg').innerHTML = state.cameraError === 'denied'
      ? t('Camera access is off for GazeStage. {open}, turn on GazeStage under Camera, then reopen the app.', { open: `<button class="linkish" id="obOpenCam">${t('Open System Settings')}</button>` })
      : t("The camera couldn't start ({error}). Check it isn't in use by another app.", { error: state.cameraError });
    $('obOpenCam')?.addEventListener('click', () => bridge?.media.openSettings('camera'));
    return;
  }
  if (ob === 'nocam') { S.mode = 'mouse'; save(); return renderStep('select'); }
  if (ob === 'mode') { S.mode = target.dataset.value; save(); filterX.reset(); filterY.reset(); if (S.mode !== 'mouse') startCamera(); return renderStep('pointer'); }
  if (ob === 'select') {
    S.select = target.dataset.value; save(); refreshChips();
    if (S.select === 'sound') await startMic(); else stopMic();
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
applyDisplay(); syncSettingsForm(); renderInstrument(); renderTone(); addProgressBars(); refreshChips(); refreshCalInfo();
synth.setVolume(+S.volume);
if (S.xyShape) synth.shape(S.xyX, S.xyY);
midi.init();
wake();
(async () => {
  if (!S.onboarded) { startOnboarding(); return; }
  if (S.mode !== 'mouse') {
    const st = bridge ? await bridge.media.status() : { camera: 'granted' };
    if (st.camera === 'granted' || st.camera === 'not-determined') await startCamera();
    else toast(t('Camera access is off. Turn it on in System Settings › Privacy & Security › Camera.'), 6000);
  }
  if (S.select === 'sound') startMic();
})();
