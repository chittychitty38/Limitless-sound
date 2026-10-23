// End-to-end smoke test. First launches the app the way the nightly proof does on a fresh Mac
// (no camera, microphone or answering sound output, nobody to answer a question) and checks it
// answers every action within a second. Then launches it with a fake camera and microphone on a
// fresh profile, walks the guided setup, plays a note, opens settings, and checks for page errors.
// On macOS it also checks that GazeStage created its own virtual MIDI ports. Then it starts
// GazeStage again on a slowed-down CPU and checks it answers every action, never freezes, and
// soon finds the face in front of the camera (face-camera.mjs).
//   npm test                the source tree (on Linux: xvfb-run -a npm test)
//   npm run test:packaged    the built app in dist/
import { _electron as electron } from 'playwright';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { faceCamera } from './face-camera.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const packaged = process.argv.includes('--packaged');
const BUILT = {
  darwin: join(root, 'dist', process.arch === 'arm64' ? 'mac-arm64' : 'mac', 'GazeStage.app', 'Contents', 'MacOS', 'GazeStage'),
  win32: join(root, 'dist', 'win-unpacked', 'GazeStage.exe'),
  linux: join(root, 'dist', 'linux-unpacked', 'gazestage'),
};
const profile = mkdtempSync(join(tmpdir(), 'gazestage-test-'));
const bareProfile = mkdtempSync(join(tmpdir(), 'gazestage-bare-'));   // first launch with no devices
const logs = mkdtempSync(join(tmpdir(), 'gazestage-logs-'));

// A stand-in Limitless Sound hub, so the test can check GazeStage joins the suite.
const hubHome = mkdtempSync(join(tmpdir(), 'gazestage-hub-'));
const hub = { hello: null, sock: null, results: new Map(), dids: [], states: {} };
const hubServer = createServer((sock) => {
  let buf = '';
  sock.on('data', (d) => {
    buf += d; let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const msg = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1);
      if (msg.op === 'hello') { hub.hello = msg; hub.sock = sock; sock.write(JSON.stringify({ op: 'welcome', protocol: 1, prefs: {}, actions: [], states: {} }) + '\n'); }
      if (msg.op === 'result') hub.results.set(msg.id, msg);
      if (msg.op === 'did') hub.dids.push(msg.action);
      if (msg.op === 'state') hub.states[msg.key] = msg.value;
    }
  });
  sock.on('error', () => {});
});
await new Promise((r) => hubServer.listen(0, '127.0.0.1', r));
writeFileSync(join(hubHome, 'link.json'), JSON.stringify({ port: hubServer.address().port, token: 'test' }));
const hubInvoke = async (id, action, args = {}) => {
  hub.sock.write(JSON.stringify({ op: 'invoke', id, action, args, source: 'voice', depth: 0 }) + '\n');
  for (let t = 0; t < 50 && !hub.results.has(id); t++) await new Promise((r) => setTimeout(r, 100));
  return hub.results.get(id);
};
const flags = ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--user-data-dir=${profile}`];
const env = { ...process.env, LIMITLESS_SOUND_HOME: hubHome, LIMITLESS_SOUND_LOGS: logs };
const launch = (more = [], base = flags) => electron.launch(packaged
  ? { executablePath: BUILT[process.platform], args: [...base, ...more], env }
  : { executablePath: createRequire(import.meta.url)('electron'), args: [root, ...base, ...more], env });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// The page's longest freeze: the slowest round trip to its thread while watching.
const freezeWatch = (page) => {
  const w = { longest: 0, on: true };
  w.done = (async () => {
    while (w.on) {
      const t = Date.now(); await page.evaluate(() => 0).catch(() => {});
      w.longest = Math.max(w.longest, Date.now() - t); await sleep(25);
    }
  })();
  w.stop = async () => { w.on = false; await w.done; return w.longest; };
  return w;
};
// Presses every action GazeStage announced, one after another like the Access Standard test kit,
// and times each answer.
const pressAll = async (firstId) => {
  const answers = [];
  for (const [n, { id: action }] of hub.hello.actions.entries()) {
    const id = firstId + n, sent = Date.now();
    hub.sock.write(JSON.stringify({ op: 'invoke', id, action, args: {}, source: 'kit', depth: 0 }) + '\n');
    while (!hub.results.has(id) && Date.now() - sent < 3000) await sleep(5);
    answers.push({ action, ms: Date.now() - sent, result: hub.results.get(id) });
  }
  return answers;
};
// The built-in instrument's hidden page (synth.html), where its notes sound.
const synthPage = async (electronApp) => {
  for (let t = 0; t < 100; t++) {
    const page = electronApp.windows().find((p) => p.url().endsWith('/synth.html'));
    if (page) return page;
    await sleep(100);
  }
  throw new Error('the built-in instrument has no page');
};

const step = (name) => console.log('•', name);
let app = null;
try {
  step('first launch with no camera, microphone or working sound output: every action answered within a second');
  // Like the nightly proof on a fresh Mac: a fresh profile, no fake devices, nobody to answer a
  // question. Making an audio context waits for the computer's audio device, twice, up to 10 s
  // each: on a Mac without a working one, the first transport click froze the window for 20 s
  // and 8 of 10 actions went unanswered. Here the audio stops answering too (Chromium's audio
  // service is paused, except on Windows, which can't), and a note starts the built-in sound
  // first: the window must still answer every action within a second and never freeze.
  app = await launch([], ['--no-sandbox', `--user-data-dir=${bareProfile}`]);
  const bare = await app.firstWindow();
  for (let t = 0; t < 300 && !hub.hello; t++) await sleep(100);
  assert.ok(hub.hello, 'joins Limitless Sound on first launch');
  // The Access Standard's rule for actions (C3 in standard/conformance/las_check.py): a short id of
  // letters, digits and _, and a plain label. The tone pad's first ids (xy.set) broke it, and only
  // the proof noticed: GazeStage 0.4.1 lost its level.
  const badActions = hub.hello.actions.filter((a) => !/^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(a.id) || !a.label?.trim() || a.label.length > 60);
  assert.deepEqual(badActions.map((a) => a.id), [], 'every action has a short id and a plain label');
  assert.equal(await bare.evaluate(() => window.__gs.S.onboarded), false, 'first launch: the guided setup is showing');
  const watch = freezeWatch(bare);
  let audio = null;
  if (process.platform !== 'win32') {
    await bare.evaluate(() => navigator.mediaDevices.enumerateDevices());   // starts the audio service
    audio = (await app.evaluate(({ app: a }) => a.getAppMetrics())).find((m) => /audio/i.test(m.serviceName || ''));
    if (audio) process.kill(audio.pid, 'SIGSTOP');
  }
  let answers, frozen;
  try {
    await bare.evaluate(() => setTimeout(() => document.querySelector('#pads .target')
      .dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }))));
    answers = await pressAll(200);
    frozen = await watch.stop();
  } finally { if (audio) process.kill(audio.pid, 'SIGCONT'); }
  step(`${answers.map((a) => `${a.action} ${a.ms} ms`).join(', ')}; longest freeze ${frozen} ms${audio ? ', the audio stopped' : ''}`);
  const slow = answers.filter((a) => !a.result || a.ms > 1000 || /didn’t answer|still starting/.test(a.result.message));
  assert.deepEqual(slow.map((a) => `${a.action}: ${a.result ? a.result.message : 'no answer'} (${a.ms} ms)`), [], 'every action answered within a second');
  assert.ok(frozen < 1000, `the window froze for ${frozen} ms`);
  const pages = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()
    .map((w) => ({ page: w.webContents.getURL().split('/').pop(), pid: w.webContents.getOSProcessId(), shown: w.isVisible() })));
  const uiProc = pages.find((p) => p.page === 'index.html'), synthProc = pages.find((p) => p.page === 'synth.html');
  assert.ok(uiProc && synthProc && uiProc.pid !== synthProc.pid && !synthProc.shown,
    `the built-in sound plays in a hidden page and process of its own: ${JSON.stringify(pages)}`);

  step('a question on screen (reset all settings) does not stop it answering either');
  // A confirm() in the page held it until someone answered. The question stays open here.
  await app.evaluate(({ dialog }) => { dialog.showMessageBox = () => new Promise((r) => { globalThis.answerQuestion = r; }); });
  await bare.evaluate(() => setTimeout(() => document.getElementById('resetAll').click()));
  for (let t = 0; t < 50 && !(await app.evaluate(() => !!globalThis.answerQuestion)); t++) await sleep(100);
  assert.ok(await app.evaluate(() => !!globalThis.answerQuestion), 'the question is asked');
  const whileAsking = (await pressAll(300)).filter((a) => !a.result || a.ms > 1000 || /didn’t answer|still starting/.test(a.result.message));
  assert.deepEqual(whileAsking.map((a) => a.action), [], 'every action answered within a second while the question is open');
  await app.evaluate(() => globalThis.answerQuestion({ response: 1 }));   // Cancel

  step('sitting idle, the window neither lays itself out nor asks to be drawn');
  // Rewriting the status chips every second and asking for a frame 4 times a second kept a
  // Mac's CPU busy (about 2.2%) while nothing changed on screen.
  await sleep(4000);   // the toasts and flashes from the actions above are over
  const metrics = await bare.context().newCDPSession(bare);
  await metrics.send('Performance.enable');
  const layouts = async () => (await metrics.send('Performance.getMetrics')).metrics.find((m) => m.name === 'LayoutCount').value;
  await bare.evaluate(() => {
    const ask = window.requestAnimationFrame.bind(window);
    window.__frames = 0; window.requestAnimationFrame = (f) => { window.__frames++; return ask(f); };
  });
  const laidOut = await layouts();
  await sleep(5000);   // longer than anything GazeStage checks now and then (the tone pad's output, every 4 s)
  const idle = { layouts: await layouts() - laidOut, frames: await bare.evaluate(() => window.__frames) };
  assert.deepEqual(idle, { layouts: 0, frames: 0 }, `in 5 s sitting idle: ${JSON.stringify(idle)}`);
  await app.close();
  hub.hello = null;

  app = await launch();
  const win = await app.firstWindow();
  const errors = [];
  win.on('pageerror', (e) => errors.push(e.message));
  win.on('console', (m) => { if (m.type() === 'error' && !/XNNPACK|GL Driver|WebGL|^smoke test:/.test(m.text())) errors.push(m.text()); });
  await win.waitForLoadState();
  await win.setViewportSize({ width: 1280, height: 800 });
  assert.equal(await win.title(), 'GazeStage');

  step('guided setup appears on first launch');
  await win.waitForSelector('#onboard.show');
  await win.click('[data-ob=next]');

  step('camera starts and the face model loads offline');
  await win.click('[data-ob=camera]');
  await win.waitForFunction(() => window.__gs.state.cameraOn || window.__gs.state.cameraState === 'error', null, { timeout: 90000 });
  assert.equal(await win.evaluate(() => window.__gs.state.cameraState === 'error' ? window.__gs.state.cameraError : 'ok'), 'ok');
  await win.click('[data-ob=next]');

  step('keeps a log file: how it started, the face tracking it runs, and what the page reports');
  await win.evaluate(() => { for (let i = 0; i < 3; i++) console.error('smoke test: an error the page reports'); console.log('smoke test: not an error'); });
  const logText = () => { try { return readFileSync(join(logs, 'GazeStage.log'), 'utf8'); } catch { return ''; } };
  const bothLogged = () => /Face tracking: /.test(logText()) && /Page: smoke test/.test(logText());
  for (let t = 0; t < 100 && !bothLogged(); t++) await new Promise((r) => setTimeout(r, 100));
  const logged = logText();
  assert.match(logged, /^\d{4}-\d\d-\d\d [\d:,]+ INFO    GazeStage: Started GazeStage \d+\.\d+\.\d+ on /);
  assert.match(logged, /INFO    GazeStage: Face tracking: (CPU|GPU), /);
  assert.equal(logged.match(/ERROR   GazeStage: Page: smoke test: an error the page reports/g)?.length, 1, logged);
  assert.doesNotMatch(logged, /not an error/);

  step('pointer and select choices');
  await win.click('[data-ob=mode][data-value=head]');
  await win.click('[data-ob=next]');
  await win.click('[data-ob=select][data-value=sound]');
  await win.waitForTimeout(500);
  assert.doesNotMatch(await win.textContent('#toast'), /Microphone access is off/);
  assert.equal(await win.evaluate(() => window.__gs.listening()), true, 'the sound switch listens');
  await win.click('[data-ob=select][data-value=dwell]');
  assert.equal(await win.evaluate(() => window.__gs.listening()), false, 'choosing dwell closes the microphone');
  await win.click('[data-ob=next]');

  step('practice targets');
  await win.waitForSelector('[data-practice="1"]');
  await win.waitForFunction(() => !window.__gs.state.calibrating, null, { timeout: 20000 });
  for (const n of [1, 2, 3]) await win.click(`[data-practice="${n}"]`);
  assert.match(await win.textContent('#practiceMsg'), /Nicely done/);
  await win.click('[data-ob=next]');
  await win.click('[data-ob=finish-play]');
  await win.waitForSelector('#onboard:not(.show)', { state: 'attached' });
  assert.equal(await win.evaluate(() => window.__gs.S.onboarded), true);

  step('instrument pads play the built-in sound');
  assert.equal(await win.locator('#pads .target').count(), 8);
  const sound = await synthPage(app);
  const voices = () => sound.evaluate(() => window.__synth.voices.size);
  const sounding = (yes) => sound.waitForFunction((y) => (window.__synth.voices.size > 0) === y, yes, { timeout: 2000 }).catch(() => {});
  const pad = win.locator('#pads .target').first();
  await pad.hover(); await win.mouse.down();
  await sounding(true);
  assert.ok(await voices() > 0, 'a note is sounding');
  await win.mouse.up();
  // After a while of silence the audio rests (a running audio context kept the computer busy
  // while idle); the next note wakes it and still plays. 10 s in use, 0.3 s here.
  await sounding(false);
  await sound.evaluate(() => { const s = window.__synth; s.allOff(); s.restMs = 300; s.restLater(); });
  await sound.waitForFunction(() => window.__synth.ctx.state === 'suspended', null, { timeout: 5000 });
  await pad.hover(); await win.mouse.down();
  await sound.waitForFunction(() => window.__synth.ctx.state === 'running' && window.__synth.voices.size > 0,
    null, { timeout: 3000 });
  await win.mouse.up();
  await sound.evaluate(() => { window.__synth.restMs = 10000; window.__synth.restLater(); });
  await win.click('[data-action=chords]');
  assert.match(await win.locator('#pads .target').first().textContent(), /^[A-G][♯]?(m|°|\+)?/);

  step('a held switch is released when the window loses focus');
  await win.evaluate(() => { window.__gs.S.mode = 'mouse'; window.__gs.S.select = 'switch'; });
  const target = win.locator('#pads .target').nth(5);
  const padId = await target.getAttribute('data-pad');
  const box = await target.boundingBox();
  await win.evaluate(() => document.activeElement?.blur());
  // With the sound resting, the pointer settling on a pad wakes it before anything is pressed,
  // so the first note after a rest isn't late.
  await win.mouse.move(5, 5);
  await sound.evaluate(() => { window.__synth.restMs = 300; window.__synth.restLater(); });
  await sound.waitForFunction(() => window.__synth.ctx.state === 'suspended', null, { timeout: 5000 });
  await win.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  // Wait until the pointer has settled on the pad (slower on CI runners than locally).
  await win.waitForFunction((id) => window.__gs.state.current?.dataset.pad === id, padId, { timeout: 5000 });
  await sound.waitForFunction(() => window.__synth.ctx.state === 'running', null, { timeout: 3000 });
  assert.equal(await voices(), 0, 'woken by the pointer alone: nothing is sounding yet');
  await sound.evaluate(() => { window.__synth.restMs = 10000; window.__synth.restLater(); });
  await win.keyboard.down('Space');
  await sounding(true);
  assert.ok(await voices() > 0, 'the switch plays the pad');
  await win.evaluate(() => window.dispatchEvent(new Event('blur')));
  await sounding(false);
  assert.equal(await voices(), 0, 'losing focus stops the note');
  await win.keyboard.up('Space');
  await win.keyboard.down('Space');
  await sounding(true);
  assert.ok(await voices() > 0, 'the next press still works');
  await win.keyboard.up('Space');
  await sounding(false);
  assert.equal(await voices(), 0, 'key-up releases the note');
  await win.evaluate(() => { window.__gs.S.mode = 'head'; window.__gs.S.select = 'dwell'; });
  await win.mouse.move(5, 5);

  step('joins Limitless Sound and takes actions from other apps');
  await win.waitForFunction(() => window.__gs.suite(), null, { timeout: 10000 });
  assert.equal(hub.hello.tool, 'gaze');
  assert.ok(hub.hello.actions.some((a) => a.id === 'record' && a.intent === 'daw.record'));
  const octave = await win.evaluate(() => +window.__gs.S.octave);
  const up = await hubInvoke(1, 'octaveUp');
  assert.equal(up?.ok, true, JSON.stringify(up));
  assert.equal(await win.evaluate(() => +window.__gs.S.octave), Math.min(7, octave + 1));
  const nope = await hubInvoke(2, 'fly');
  assert.equal(nope?.ok, false);
  const shown = await hubInvoke(3, 'transport');
  assert.equal(shown?.ok, true);
  assert.equal(await win.evaluate(() => window.__gs.state.page), 'transport');
  await hubInvoke(4, 'pads');

  step('tone pad: two controllers from one point');
  // On macOS, listen on GazeStage Notes like Pro Tools or a plugin would.
  const heard = [];
  let listener = null;
  if (process.platform === 'darwin') {
    const { Input } = createRequire(import.meta.url)('@julusian/midi');
    listener = new Input();
    for (let i = 0; i < listener.getPortCount(); i++) if (listener.getPortName(i) === 'GazeStage Notes') { listener.openPort(i); break; }
    listener.on('message', (_dt, m) => heard.push(m));
  }
  await win.evaluate(() => {
    const g = window.__gs; g.sent = [];
    const send = g.midi.sendTone.bind(g.midi);
    g.midi.sendTone = (b) => { for (let i = 0; i + 2 < b.length; i += 3) g.sent.push([b[i], b[i + 1], b[i + 2]]); return send(b); };
    // Switch mode, so the mouse resting on a button never dwells it by accident.
    Object.assign(g.S, { mode: 'mouse', select: 'switch', xyGlide: 0 });
  });
  await win.click('[data-goto=tone]');
  assert.equal(await win.evaluate(() => window.__gs.state.page), 'tone');
  const xyBox = await win.locator('#xy').boundingBox();
  const at = (u, v) => [xyBox.x + u * xyBox.width, xyBox.y + (1 - v) * xyBox.height];
  const lastCC = (cc) => win.evaluate((c) => window.__gs.sent.filter((m) => m[1] === c).at(-1)?.[2] ?? null, cc);
  const near = (a, b) => a != null && Math.abs(a - b) <= 2;
  await win.mouse.click(...at(0.75, 0.75));
  await win.waitForTimeout(150);
  assert.ok(near(await lastCC(16), 95) && near(await lastCC(17), 95), `a click places the point: ${await lastCC(16)}, ${await lastCC(17)}`);
  assert.ok((await win.evaluate(() => window.__gs.sent[0][0])) === 0xb0, 'control changes on channel 1');

  step('tone pad: look and hold still to place');
  await win.evaluate(() => { window.__gs.S.select = 'dwell'; });
  await win.mouse.move(...at(0.25, 0.3));
  await win.waitForFunction(() => Math.abs(window.__gs.motion.x - 0.25) < 0.03, null, { timeout: 4000 });
  await win.waitForTimeout(100);
  assert.ok(near(await lastCC(16), 32) && near(await lastCC(17), 38), `placed by dwell: ${await lastCC(16)}, ${await lastCC(17)}, at ${await win.evaluate(() => [window.__gs.motion.x, window.__gs.motion.y])}`);

  await win.evaluate(() => { window.__gs.S.select = 'switch'; });

  step('tone pad: arrows, saved tones and glide');
  const before = await win.evaluate(() => window.__gs.motion.x);
  await win.click('[data-nudge=right]');
  await win.waitForTimeout(300);
  assert.ok(await win.evaluate(() => window.__gs.motion.x) > before + 0.03, 'right arrow steps right');
  await win.click('[data-snap=A]');
  await win.waitForTimeout(100);
  assert.deepEqual(await win.evaluate(() => [window.__gs.motion.x, window.__gs.motion.y]), [0.2, 0.8]);
  await win.click('[data-action=xyCenter]');
  await win.click('[data-action=xyStore]');
  await win.click('[data-snap=D]');
  assert.deepEqual(await win.evaluate(() => window.__gs.S.xySnaps.D), [0.5, 0.5]);
  await win.click('[data-action=xyGlide]');
  assert.equal(await win.evaluate(() => window.__gs.S.xyGlide), 250);

  step('tone pad: Listen holds a chord on the built-in sound, shaped by the pad');
  await win.click('[data-action=xyListen]');
  await sounding(true);
  assert.ok(await voices() >= 3, `a chord is sounding: ${await voices()} notes`);
  assert.deepEqual(await sound.evaluate(() => window.__synth.shaping), await win.evaluate(() => [window.__gs.motion.x, window.__gs.motion.y]),
    'the built-in sound has the pad\'s shape');
  await win.click('[data-action=xyListen]');
  await sounding(false);
  assert.equal(await voices(), 0, 'Listen again lets the chord go');
  await win.mouse.move(5, 5);

  step('tone pad: other Limitless Sound apps can move it');
  assert.ok(hub.hello.actions.some((a) => a.id === 'xySet'));
  const set = await hubInvoke(5, 'xySet', { x: 0, y: 127, glide: 0 });
  assert.equal(set?.ok, true, JSON.stringify(set));
  await win.waitForTimeout(100);
  assert.deepEqual([await lastCC(16), await lastCC(17)], [0, 127]);
  assert.equal((await hubInvoke(6, 'xySnapC'))?.ok, true);
  if (listener) {
    await win.waitForTimeout(300);
    listener.closePort();
    assert.ok(heard.some((m) => m[0] === 0xb0 && m[1] === 16 && m[2] === 0), `GazeStage Notes carried the tone pad: ${JSON.stringify(heard.slice(-4))}`);
  }

  step('tone pad: moves and sends with GazeStage minimised, as when the DAW is in front');
  // Drawing stops while the window is minimised; the tone pad's MIDI must not wait for it. It
  // used to move with the drawing: "tone A" from Voice waited for GazeStage to be looked at.
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().find((w) => w.isVisible())?.minimize());
  await win.evaluate(() => {   // and, wherever minimising doesn't stop it (a test display), no frames
    const ask = window.requestAnimationFrame.bind(window), held = [];
    window.requestAnimationFrame = (f) => { held.push(f); return 0; };
    window.__framesBack = () => { window.requestAnimationFrame = ask; held.forEach((f) => ask(f)); };
  });
  await sleep(500);
  const asked = Date.now();
  assert.equal((await hubInvoke(7, 'xySet', { x: 127, y: 0, glide: 300 }))?.ok, true);
  await win.waitForFunction(() => window.__gs.sent.filter((m) => m[1] === 16).at(-1)?.[2] === 127, null, { polling: 20, timeout: 3000 });
  const glided = Date.now() - asked;
  assert.ok(glided < 1000, `a 300 ms glide finished ${glided} ms after the action, with the window minimised`);
  assert.equal(await win.evaluate(() => window.__gs.sent.filter((m) => m[1] === 17).at(-1)?.[2]), 0);
  await win.evaluate(() => window.__framesBack());
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().find((w) => w.isMinimized())?.restore());
  await sleep(300);

  await win.evaluate(() => Object.assign(window.__gs.S, { mode: 'head', select: 'dwell' }));
  await win.click('[data-goto=play]');

  step('settings open and close');
  await win.click('#settingsBtn');
  await win.waitForSelector('#settings.open');
  await win.click('#closeSettings');

  step('transport page');
  await win.click('[data-goto=transport]');
  assert.equal(await win.locator('#transport .target').count(), 5);

  step('shared settings: text size, contrast and motion are applied and reported');
  const until = async (cond, ms = 3000) => { const end = Date.now() + ms; while (!cond() && Date.now() < end) await new Promise((r) => setTimeout(r, 25)); return cond(); };
  const sendPrefs = (prefs) => hub.sock.write(JSON.stringify({ op: 'prefs', prefs }) + '\n');
  const applied = (want, ms) => until(() => JSON.stringify(hub.states['prefs.applied']) === JSON.stringify(want), ms);
  const view = () => win.evaluate(() => {
    const r = document.documentElement, clipped = [];
    for (const t of document.querySelectorAll('.target'))
      if (t.offsetParent && (t.scrollHeight > t.clientHeight + 1 || t.scrollWidth > t.clientWidth + 1)) clipped.push(t.textContent.trim());
    return { contrast: r.dataset.contrast, motion: r.dataset.motion, text: getComputedStyle(document.body).fontSize,
      transition: getComputedStyle(document.querySelector('.target')).transitionDuration, clipped };
  });
  const systemReduce = await win.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  assert.deepEqual(hub.states['prefs.applied'], { textScale: 1, highContrast: false, reduceMotion: systemReduce }, 'reported after the welcome');
  const sentAt = Date.now();
  sendPrefs({ speak: true, oneVoice: true, textScale: 1.5, highContrast: true, reduceMotion: true, dwellMs: 1500, scanMs: 2000 });
  assert.ok(await applied({ textScale: 1.5, highContrast: true, reduceMotion: true }), JSON.stringify(hub.states['prefs.applied']));
  assert.ok(Date.now() - sentAt < 3000, 'within 3 seconds');
  assert.deepEqual(await view(), { contrast: 'high', motion: 'reduce', text: '25.5px', transition: '0s', clipped: [] });
  assert.equal(await win.evaluate(() => window.__gs.S.dwell), 900, 'GazeStage keeps its own dwell time');
  sendPrefs({ textScale: 2, highContrast: true, reduceMotion: true });
  assert.ok(await applied({ textScale: 2, highContrast: true, reduceMotion: true }));
  assert.deepEqual((await view()).clipped, [], 'nothing clips at double size');
  await win.click('[data-goto=play]');
  assert.deepEqual((await view()).clipped, [], 'nothing clips at double size');

  step('shared settings: the more accessible setting wins');
  const own = (id, value) => win.evaluate(([i, v]) => { const el = document.getElementById(i); if (el.type === 'checkbox') el.checked = v; else el.value = v; el.dispatchEvent(new Event('change')); }, [id, value]);
  await own('sSize', 'xlarge'); await own('sContrast', true);
  sendPrefs({ textScale: 1, highContrast: false, reduceMotion: false });
  assert.ok(await applied({ textScale: 1.41, highContrast: true, reduceMotion: systemReduce }), JSON.stringify(hub.states['prefs.applied']));
  assert.equal((await view()).text, '24px');
  await own('sSize', 'normal'); await own('sContrast', false);
  assert.ok(await applied({ textScale: 1, highContrast: false, reduceMotion: systemReduce }));
  assert.deepEqual(await view(), { contrast: 'normal', motion: systemReduce ? 'reduce' : 'normal', text: '17px', transition: systemReduce ? '0s' : '0.12s, 0.12s, 0.12s', clipped: [] });

  step('shared settings: reduced motion draws dwell in steps and still waits the full dwell');
  sendPrefs({ reduceMotion: true });
  assert.ok(await applied({ textScale: 1, highContrast: false, reduceMotion: true }));
  // A long dwell, so firing a step early would show even at the test machine's slow frame rate.
  await win.evaluate(() => { Object.assign(window.__gs.state, { px: 5, py: 5 }); Object.assign(window.__gs.S, { mode: 'mouse', select: 'dwell', dwell: 2400 }); });
  const dwelled = win.evaluate(() => new Promise((done) => {
    const t = document.querySelector('[data-action=chords]'), bar = t.querySelector('.progress'), was = t.getAttribute('aria-pressed'), drawn = new Set();
    // Room for a slow test machine to move the mouse there first; firing early is checked below.
    const g = window.__gs, quit = setTimeout(() => done({ drawn: [...drawn], fired: false }), 15000);
    const look = () => { drawn.add(bar.style.width); if (t.getAttribute('aria-pressed') === was) requestAnimationFrame(look); };
    new MutationObserver((_m, obs) => {
      obs.disconnect(); clearTimeout(quit);
      done({ drawn: [...drawn], fired: true, after: performance.now() - g.state.enteredAt, dwell: g.S.dwell });
    }).observe(t, { attributes: true, attributeFilter: ['aria-pressed'] });
    look();
  }));
  const chords = await win.locator('[data-action=chords]').boundingBox();
  await win.mouse.move(chords.x + chords.width / 2, chords.y + chords.height / 2);
  const d = await dwelled;
  assert.ok(d.fired, 'dwell still selects');
  assert.ok(d.drawn.every((w) => ['', '0%', '25%', '50%', '75%', '100%'].includes(w)) && d.drawn.some((w) => /^(25|50|75)%$/.test(w)), `stepped: ${d.drawn}`);
  // The steps are drawing only: a full step shows early, but the target never fires early.
  assert.ok(d.after >= d.dwell, `fired after ${d.after} ms of ${d.dwell}`);
  await win.evaluate(() => Object.assign(window.__gs.S, { mode: 'head', dwell: 900 }));
  await win.mouse.move(5, 5);

  step('shared settings: let go when Limitless Sound goes away, and report again when it is back');
  delete hub.states['prefs.applied'];
  sendPrefs({ textScale: 1.5, highContrast: true });
  await until(() => hub.states['prefs.applied']?.highContrast);
  delete hub.states['prefs.applied'];
  hub.sock.destroy();
  await win.waitForFunction(() => document.documentElement.dataset.contrast === 'normal', null, { timeout: 3000 });
  assert.equal((await view()).text, '17px');
  assert.ok(await applied({ textScale: 1, highContrast: false, reduceMotion: systemReduce }, 8000), 'reported again after reconnecting');

  const midi = await win.evaluate(() => ({ mode: window.__gs.midi.mode, error: window.__gs.midi.error || null, native: window.__gs.midi.nativeError || null }));
  step(`MIDI mode: ${midi.mode}${midi.error ? ` (${midi.error})` : ''}${midi.native ? `; virtual ports: ${midi.native}` : ''}`);
  if (process.platform === 'darwin') assert.equal(midi.mode, 'native', 'GazeStage creates its own MIDI ports on macOS');

  assert.deepEqual(errors, []);

  step('starts again on a slow computer: answers every action within 3 seconds, never freezes');
  // Same profile, so the camera and face model start at launch, this time with a face in front
  // of the camera. The page is slowed to run like an older Intel Mac, and every action is pressed
  // the moment GazeStage joins, like the Access Standard test kit does. That's 4x, except on an
  // Intel Mac, which already is one: slowing the Intel Mac runner 4x on top made the same build
  // find the first face in 1.7 s on one run and 3.2 s on the next.
  const slowdown = process.platform === 'darwin' && process.arch === 'x64' ? 2 : 4;
  const faceVideo = await faceCamera(win, hubHome);
  await win.evaluate(() => localStorage.setItem('gazestage.settings.v3', JSON.stringify({ ...window.__gs.S, mode: 'head' })));
  await app.close();
  hub.hello = null;
  app = await launch(faceVideo ? [`--use-file-for-fake-video-capture=${faceVideo}`] : []);
  const again = await app.firstWindow();
  const tracking = [];
  again.on('pageerror', (e) => errors.push(e.message));
  again.on('console', (m) => { if (m.type() === 'error' && !/XNNPACK|GL Driver|WebGL/.test(m.text())) errors.push(m.text()); });
  again.on('console', (m) => { if (/^Face tracking:/.test(m.text())) tracking.push(m.text()); });
  const cdp = await again.context().newCDPSession(again);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: slowdown });
  const watchStart = freezeWatch(again);   // while it starts
  for (let t = 0; t < 300 && !hub.hello; t++) await sleep(100);
  assert.ok(hub.hello, 'joins Limitless Sound again');
  const unanswered = (await pressAll(100)).filter((a) => !a.result || /didn’t answer|still starting/.test(a.result.message))
    .map((a) => `${a.action}: ${a.result ? a.result.message : 'no answer in 3 s'}`);
  // Tracking runs: a face is found (or, with the plain fake camera, reported missing).
  await again.waitForFunction((face) => face ? window.__gs.state.sample?.face : window.__gs.state.cameraState === 'noface', !!faceVideo, { timeout: 90000 });
  const freeze = await watchStart.stop();
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  const first = (what) => +(tracking.find((t) => t.includes(`first ${what}`))?.match(/(\d+) ms/)?.[1] ?? NaN);
  for (let t = 0; t < 30 && Number.isNaN(first(faceVideo ? 'face' : 'frame read')); t++) await new Promise((r) => setTimeout(r, 100));
  const chosen = hub.states.faceTracking || '';
  step(`longest freeze while starting, the page slowed ${slowdown}x: ${freeze} ms`);
  step(`face tracking: ${chosen.slice(0, 60)}…; first frame ${first('frame read')} ms, first face ${faceVideo ? first('face') + ' ms' : 'not tested (offline)'}`);
  assert.deepEqual(unanswered, [], 'every action answered within 3 seconds');
  assert.ok(freeze < 1500, `the window froze for ${freeze} ms`);
  assert.match(chosen, /^(CPU|GPU), /, 'says which face tracking it runs');
  if (/software graphics/.test(chosen)) {
    // No graphics chip to speak of (as under xvfb): the CPU, straight away, and a quick first face.
    // About 1.2-1.4 s here with the page slowed 4x; the GPU delegate on software graphics
    // took 4.4-6.4 s.
    assert.match(chosen, /^CPU, /);
    const took = faceVideo ? first('face') : first('frame read');
    assert.ok(took < 3000, `first ${faceVideo ? 'face' : 'frame'} after ${took} ms`);
  }
  assert.deepEqual(errors, []);
  console.log('smoke test passed');
} finally {
  await app?.close();
  hubServer.close();
  rmSync(bareProfile, { recursive: true, force: true });
  rmSync(profile, { recursive: true, force: true });
  rmSync(hubHome, { recursive: true, force: true });
  rmSync(logs, { recursive: true, force: true });
}
