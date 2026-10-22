// End-to-end smoke test. Launches the app with a fake camera and microphone on a fresh
// profile, walks the guided setup, plays a note, opens settings, and checks for page errors.
// On macOS it also checks that GazeStage created its own virtual MIDI ports.
//   npm test                 the source tree (on Linux: xvfb-run -a npm test)
//   npm run test:packaged    the built app in dist/
import { _electron as electron } from 'playwright';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const packaged = process.argv.includes('--packaged');
const BUILT = {
  darwin: join(root, 'dist', process.arch === 'arm64' ? 'mac-arm64' : 'mac', 'GazeStage.app', 'Contents', 'MacOS', 'GazeStage'),
  win32: join(root, 'dist', 'win-unpacked', 'GazeStage.exe'),
  linux: join(root, 'dist', 'linux-unpacked', 'gazestage'),
};
const profile = mkdtempSync(join(tmpdir(), 'gazestage-test-'));

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
const hubInvoke = async (id, action) => {
  hub.sock.write(JSON.stringify({ op: 'invoke', id, action, args: {}, source: 'voice', depth: 0 }) + '\n');
  for (let t = 0; t < 50 && !hub.results.has(id); t++) await new Promise((r) => setTimeout(r, 100));
  return hub.results.get(id);
};
const flags = ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--user-data-dir=${profile}`];
const app = await electron.launch(packaged
  ? { executablePath: BUILT[process.platform], args: flags, env: { ...process.env, LIMITLESS_SOUND_HOME: hubHome } }
  : { executablePath: createRequire(import.meta.url)('electron'), args: [root, ...flags], env: { ...process.env, LIMITLESS_SOUND_HOME: hubHome } });

const step = (name) => console.log('•', name);
try {
  const win = await app.firstWindow();
  const errors = [];
  win.on('pageerror', (e) => errors.push(e.message));
  win.on('console', (m) => { if (m.type() === 'error' && !/XNNPACK|GL Driver|WebGL/.test(m.text())) errors.push(m.text()); });
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

  step('pointer and select choices');
  await win.click('[data-ob=mode][data-value=head]');
  await win.click('[data-ob=next]');
  await win.click('[data-ob=select][data-value=sound]');
  await win.waitForTimeout(500);
  assert.doesNotMatch(await win.textContent('#toast'), /Microphone access is off/);
  await win.click('[data-ob=select][data-value=dwell]');
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
  const pad = win.locator('#pads .target').first();
  await pad.hover(); await win.mouse.down();
  await win.waitForTimeout(200);
  assert.ok(await win.evaluate(() => window.__gs.synth.voices.size) > 0, 'a note is sounding');
  await win.mouse.up();
  await win.click('[data-action=chords]');
  assert.match(await win.locator('#pads .target').first().textContent(), /^[A-G][♯]?(m|°|\+)?/);

  step('a held switch is released when the window loses focus');
  await win.evaluate(() => { window.__gs.S.mode = 'mouse'; window.__gs.S.select = 'switch'; });
  const target = win.locator('#pads .target').nth(5);
  const padId = await target.getAttribute('data-pad');
  const box = await target.boundingBox();
  await win.evaluate(() => document.activeElement?.blur());
  await win.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  // Wait until the pointer has settled on the pad (slower on CI runners than locally).
  await win.waitForFunction((id) => window.__gs.state.current?.dataset.pad === id, padId, { timeout: 5000 });
  await win.keyboard.down('Space');
  await win.waitForFunction(() => window.__gs.synth.voices.size > 0, null, { timeout: 2000 }).catch(() => {});
  assert.ok(await win.evaluate(() => window.__gs.synth.voices.size) > 0, 'the switch plays the pad');
  await win.evaluate(() => window.dispatchEvent(new Event('blur')));
  assert.equal(await win.evaluate(() => window.__gs.synth.voices.size), 0, 'losing focus stops the note');
  await win.keyboard.up('Space');
  await win.keyboard.down('Space');
  await win.waitForFunction(() => window.__gs.synth.voices.size > 0, null, { timeout: 2000 }).catch(() => {});
  assert.ok(await win.evaluate(() => window.__gs.synth.voices.size) > 0, 'the next press still works');
  await win.keyboard.up('Space'); await win.waitForTimeout(100);
  assert.equal(await win.evaluate(() => window.__gs.synth.voices.size), 0, 'key-up releases the note');
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
    const g = window.__gs, quit = setTimeout(() => done({ drawn: [...drawn], fired: false }), 5000);
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
  console.log('smoke test passed');
} finally {
  await app.close();
  hubServer.close();
  rmSync(profile, { recursive: true, force: true });
  rmSync(hubHome, { recursive: true, force: true });
}
