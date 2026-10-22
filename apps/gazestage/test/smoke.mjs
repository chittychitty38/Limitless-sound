// End-to-end smoke test. Launches the app with a fake camera and microphone on a fresh
// profile, walks the guided setup, plays a note, opens settings, and checks for page errors.
// On macOS it also checks that GazeStage created its own virtual MIDI ports. Then it starts
// GazeStage again on a slowed-down CPU and checks it answers every action and never freezes.
//   npm test                the source tree (on Linux: xvfb-run -a npm test)
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
const hub = { hello: null, sock: null, results: new Map(), dids: [] };
const hubServer = createServer((sock) => {
  let buf = '';
  sock.on('data', (d) => {
    buf += d; let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const msg = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1);
      if (msg.op === 'hello') { hub.hello = msg; hub.sock = sock; sock.write(JSON.stringify({ op: 'welcome', protocol: 1, prefs: {}, actions: [], states: {} }) + '\n'); }
      if (msg.op === 'result') hub.results.set(msg.id, msg);
      if (msg.op === 'did') hub.dids.push(msg.action);
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
const launch = () => electron.launch(packaged
  ? { executablePath: BUILT[process.platform], args: flags, env: { ...process.env, LIMITLESS_SOUND_HOME: hubHome } }
  : { executablePath: createRequire(import.meta.url)('electron'), args: [root, ...flags], env: { ...process.env, LIMITLESS_SOUND_HOME: hubHome } });
let app = await launch();

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

  const midi = await win.evaluate(() => ({ mode: window.__gs.midi.mode, error: window.__gs.midi.error || null, native: window.__gs.midi.nativeError || null }));
  step(`MIDI mode: ${midi.mode}${midi.error ? ` (${midi.error})` : ''}${midi.native ? `; virtual ports: ${midi.native}` : ''}`);
  if (process.platform === 'darwin') assert.equal(midi.mode, 'native', 'GazeStage creates its own MIDI ports on macOS');

  assert.deepEqual(errors, []);

  step('starts again on a slow computer: answers every action within 3 seconds, never freezes');
  // Same profile, so the camera and face model start at launch. The page is slowed 4x, like an
  // older Intel Mac, and every action is pressed the moment GazeStage joins, like the Access
  // Standard test kit does.
  await win.evaluate(() => localStorage.setItem('gazestage.settings.v3', JSON.stringify({ ...window.__gs.S, mode: 'head' })));
  await app.close();
  hub.hello = null;
  app = await launch();
  const again = await app.firstWindow();
  again.on('pageerror', (e) => errors.push(e.message));
  again.on('console', (m) => { if (m.type() === 'error' && !/XNNPACK|GL Driver|WebGL/.test(m.text())) errors.push(m.text()); });
  const cdp = await again.context().newCDPSession(again);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  // The page's longest freeze: the slowest round trip to its thread while it starts.
  let freeze = 0, watching = true;
  const watcher = (async () => {
    while (watching) {
      const t = Date.now(); await again.evaluate(() => 0).catch(() => {});
      freeze = Math.max(freeze, Date.now() - t); await new Promise((r) => setTimeout(r, 25));
    }
  })();
  for (let t = 0; t < 300 && !hub.hello; t++) await new Promise((r) => setTimeout(r, 100));
  assert.ok(hub.hello, 'joins Limitless Sound again');
  const unanswered = [];
  for (const [n, { id: action }] of hub.hello.actions.entries()) {
    const id = 100 + n, sent = Date.now();
    hub.sock.write(JSON.stringify({ op: 'invoke', id, action, args: {}, source: 'kit', depth: 0 }) + '\n');
    while (!hub.results.has(id) && Date.now() - sent < 3000) await new Promise((r) => setTimeout(r, 10));
    const r = hub.results.get(id);
    if (!r || /didn’t answer|still starting/.test(r.message)) unanswered.push(`${action}: ${r ? r.message : 'no answer in 3 s'}`);
  }
  await again.waitForFunction(() => window.__gs.state.cameraState === 'noface', null, { timeout: 90000 });   // tracking runs
  watching = false; await watcher;
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  step(`longest freeze while starting: ${freeze} ms`);
  assert.deepEqual(unanswered, [], 'every action answered within 3 seconds');
  assert.ok(freeze < 1500, `the window froze for ${freeze} ms`);
  assert.deepEqual(errors, []);
  console.log('smoke test passed');
} finally {
  await app.close();
  hubServer.close();
  rmSync(profile, { recursive: true, force: true });
  rmSync(hubHome, { recursive: true, force: true });
}
