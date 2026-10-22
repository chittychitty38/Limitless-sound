// GazeStage under a long tracking session, switch floods, lost focus and relaunches.
//
//   cd apps/gazestage && npm ci && xvfb-run -a node ../../stress/gazestage_stress.mjs [--packaged]
//
// Uses Chromium's fake camera and microphone, so it runs on CI machines without a webcam.
// The soak runs for STRESS_SECONDS, never less than 2 minutes (the face model's memory takes
// about a minute to settle). Exits non-zero if any check fails, after running them all.
import { createRequire } from 'node:module';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const appDir = process.cwd();
const require = createRequire(join(appDir, 'package.json'));
const { _electron: electron } = require('playwright');
const packaged = process.argv.includes('--packaged');
const SECONDS = Math.max(120, Number(process.env.STRESS_SECONDS || 0));
const BUILT = {
  darwin: join(appDir, 'dist', process.arch === 'arm64' ? 'mac-arm64' : 'mac', 'GazeStage.app', 'Contents', 'MacOS', 'GazeStage'),
  win32: join(appDir, 'dist', 'win-unpacked', 'GazeStage.exe'),
  linux: join(appDir, 'dist', 'linux-unpacked', 'gazestage'),
};

const failures = [];
function check(ok, what) {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) failures.push(what);
}

async function launch() {
  const profile = mkdtempSync(join(tmpdir(), 'gazestage-stress-'));
  const flags = ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--user-data-dir=${profile}`];
  const app = await electron.launch(packaged
    ? { executablePath: BUILT[process.platform], args: flags }
    : { executablePath: require('electron'), args: [appDir, ...flags] });
  const win = await app.firstWindow();
  const errors = [];
  win.on('pageerror', (e) => errors.push(e.message));
  win.on('console', (m) => { if (m.type() === 'error' && !/XNNPACK|GL Driver|WebGL|^INFO/.test(m.text())) errors.push(m.text()); });
  await win.waitForLoadState();
  await win.setViewportSize({ width: 1280, height: 800 });
  const close = async () => { await app.close(); rmSync(profile, { recursive: true, force: true }); };
  return { app, win, sound: await synthPage(app), errors, close };
}

// The built-in instrument plays in a hidden page of its own (synth.html): its notes are counted there.
async function synthPage(app) {
  for (let t = 0; t < 100; t++) {
    const page = app.windows().find((p) => p.url().endsWith('/synth.html'));
    if (page) return page;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('the built-in instrument has no page');
}

// Go through the guided setup quickly, then put the app on the note pads with the mouse as pointer.
async function ready(win, { select = 'switch', camera = false } = {}) {
  await win.waitForSelector('#onboard.show');
  await win.click('[data-ob=next]');
  if (camera) {
    await win.click('[data-ob=camera]');
    await win.waitForFunction(() => window.__gs.state.cameraOn || window.__gs.state.cameraState === 'error', null, { timeout: 90000 });
  }
  await win.evaluate(() => {
    window.__gs.S.onboarded = true;
    window.__gs.state.onboardStep = null;
    document.getElementById('onboard').classList.remove('show');
  });
  await win.evaluate((sel) => Object.assign(window.__gs.S, { mode: 'mouse', select: sel, hold: false, chords: false }), select);
  const goto = win.locator('[data-goto=play]');
  if (await goto.count()) await goto.first().click({ force: true });
  await win.waitForFunction(() => document.querySelectorAll('#pads .target').length > 0 && window.__gs.state.page === 'play', null, { timeout: 5000 });
}

const sounding = async (win, sound) => ({
  voices: await sound.evaluate(() => window.__synth.voices.size),
  ...(await win.evaluate(() => ({ lit: document.querySelectorAll('#pads .target.on').length, held: !!window.__gs.state.heldHui }))),
});

async function hoverPad(win, i) {
  const box = await win.locator('#pads .target').nth(i).boundingBox();
  await win.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 3 });
  // Let sticky targeting settle on it: usually ~50 ms, longer on a busy test machine just after launch.
  await win.waitForFunction((n) => window.__gs.state.current === document.querySelectorAll('#pads .target')[n],
    i, { timeout: 5000 }).catch(() => {});
  await win.waitForTimeout(200);  // and let whatever that started or stopped finish
}

// Whether a note starts sounding within 2 s (a fixed short wait failed on busy test machines).
const plays = (sound) => sound.waitForFunction(() => window.__synth.voices.size > 0, null, { timeout: 2000 })
  .then(() => true, () => false);

// 1. The musician holds a note with a switch, then clicks into Pro Tools. The key-up goes to
//    Pro Tools, never to GazeStage. The note must stop and the switch must keep working.
async function focusLoss() {
  const { win, sound, close } = await launch();
  try {
    await ready(win, { select: 'switch' });
    await hoverPad(win, 0);
    await win.keyboard.down('Space');
    check(await plays(sound), 'a switch press on a gazed pad plays the note');
    // What the window sees when another app takes focus.
    await win.evaluate(() => { window.dispatchEvent(new Event('blur')); });
    await win.waitForTimeout(700);
    const after = await sounding(win, sound);
    check(after.voices === 0 && after.lit === 0,
      `the note stops when GazeStage loses focus with the switch held (voices ${after.voices}, lit pads ${after.lit})`);
    await hoverPad(win, 3);
    const moved = await sounding(win, sound);
    check(moved.voices === 0, `looking away from the pad after focus came back releases it (voices ${moved.voices})`);
    // Back in GazeStage: the key-up was lost to the other app. The next press must still play.
    await win.evaluate(() => { window.dispatchEvent(new Event('focus')); window.__gs.synth.allOff(); });
    await hoverPad(win, 2);
    await win.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', code: 'Space' })));
    check(await plays(sound), 'the switch still works after its key-up was lost to another app');
  } finally {
    await close();
  }
}

// 2. A tremor on a switch: hundreds of fast presses while the pointer wanders across the pads.
//    Afterwards nothing may be left sounding.
async function switchFlood() {
  const { win, sound, errors, close } = await launch();
  try {
    await ready(win, { select: 'switch' });
    const count = await win.locator('#pads .target').count();
    for (let i = 0; i < 300; i++) {
      if (i % 7 === 0) await hoverPad(win, i % count);
      await win.keyboard.down('Space');
      await win.waitForTimeout(i % 3 === 0 ? 30 : 5);
      await win.keyboard.up('Space');
    }
    await win.mouse.move(5, 5);
    await win.waitForTimeout(800);
    const s = await sounding(win, sound);
    check(s.voices === 0 && s.lit === 0, `nothing left sounding after 300 shaky switch presses (voices ${s.voices}, lit pads ${s.lit})`);
    check(errors.length === 0, `no errors during the switch flood (${errors.slice(0, 3).join(' | ')})`);
  } finally {
    await close();
  }
}

// 3. Dwell across the targets as fast as the settings allow, changing scale and octave as it goes.
async function dwellFlood() {
  const { win, sound, errors, close } = await launch();
  try {
    await ready(win, { select: 'dwell' });
    await win.evaluate(() => Object.assign(window.__gs.S, { dwell: 300, padDwell: 0 }));
    for (let round = 0; round < 40; round++) {
      for (const sel of ['[data-action=octdown]', '[data-action=scale]', '#pads .target']) {
        const t = win.locator(sel).first();
        if (!(await t.count())) continue;
        const b = await t.boundingBox();
        if (b) await win.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 2 });
        await win.waitForTimeout(sel.startsWith('#pads') ? 150 : 450);
      }
    }
    await win.mouse.move(5, 5);
    await win.waitForTimeout(800);
    const s = await sounding(win, sound);
    check(s.voices === 0 && s.lit === 0, `nothing left sounding after 120 fast dwell selections (voices ${s.voices}, lit ${s.lit})`);
    check(await win.locator('#pads .target').count() >= 6, 'the pads are still there after flipping scales and octaves');
    check(errors.length === 0, `no errors during the dwell flood (${errors.slice(0, 3).join(' | ')})`);
  } finally {
    await close();
  }
}

// 4. A long tracking session. Memory must level off; the frame rate is reported.
async function soak() {
  const { app, win, errors, close } = await launch();
  try {
    await ready(win, { select: 'dwell', camera: true });
    await win.evaluate(() => { window.__gs.S.mode = 'head'; });
    const camera = await win.evaluate(() => window.__gs.state.cameraState);
    check(camera !== 'error', `camera and face model start (${camera})`);
    const samples = [];
    const start = Date.now();
    while (Date.now() - start < SECONDS * 1000) {
      await win.waitForTimeout(5000);
      const metrics = await app.evaluate(({ app }) => app.getAppMetrics());
      samples.push(metrics.reduce((sum, m) => sum + (m.memory?.workingSetSize || 0), 0) / 1024);
    }
    const second = samples.slice(Math.floor(samples.length / 2));
    const growth = second[second.length - 1] - second[0];
    const fps = await win.evaluate(() => new Promise((res) => {
      let n = 0; const t0 = performance.now();
      const f = () => { n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else res(n / 2); };
      requestAnimationFrame(f);
    }));
    console.log(`     soak ${SECONDS}s: memory ${samples.map((s) => s.toFixed(0)).join(' → ')} MB`);
    // CI machines have no graphics chip, so the frame rate is reported, not judged. On a real Mac expect 30+.
    console.log(`     pointer updates at ${fps.toFixed(0)} frames/s while tracking`);
    check(growth < 60, `memory levels off in a ${SECONDS}s tracking session (+${growth.toFixed(0)} MB over the second half)`);
    check(errors.length === 0, `no errors during the session (${errors.slice(0, 3).join(' | ')})`);
  } finally {
    await close();
  }
}

// 5. Quit and reopen again and again (what a crash-and-relaunch looks like). Every launch comes up clean.
async function relaunch() {
  let ok = 0;
  for (let i = 0; i < 5; i++) {
    const { win, errors, close } = await launch();
    try {
      await win.waitForSelector('#onboard.show', { timeout: 30000 });
      await win.click('[data-ob=next]');
      await win.click('[data-ob=camera]');
      await win.waitForFunction(() => window.__gs.state.cameraOn || window.__gs.state.cameraState === 'error', null, { timeout: 90000 });
      if (await win.evaluate(() => window.__gs.state.cameraOn) && errors.length === 0) ok++;
    } finally {
      await close();
    }
  }
  check(ok === 5, `${ok} of 5 back-to-back launches started the camera cleanly`);
}

// 6. Left open while the musician works in the DAW: with nothing moving, GazeStage barely draws.
//    (Hit-testing every target 60 times a second used about 6% of the CPU for nothing.)
async function quiet() {
  const { win, close } = await launch();
  try {
    await ready(win, { select: 'dwell' });
    await win.mouse.move(2, 2);
    await win.waitForTimeout(500);
    const frames = await win.evaluate(() => new Promise((done) => {
      let n = 0;
      const raf = window.requestAnimationFrame.bind(window);
      window.requestAnimationFrame = (cb) => { n++; return raf(cb); };
      setTimeout(() => { window.requestAnimationFrame = raf; done(n); }, 2000);
    }));
    check(frames <= 20, `sitting still, it draws ${frames} frames in 2 s (at most 20)`);
    await hoverPad(win, 1);
    check(await win.waitForFunction(() => window.__gs.state.fired, null, { timeout: 5000 }).then(() => true, () => false),
      'moving onto a pad wakes it at once: the dwell fills and fires');
  } finally {
    await close();
  }
}

for (const t of [focusLoss, switchFlood, dwellFlood, quiet, relaunch, soak]) {
  try {
    await t();
  } catch (e) {
    check(false, `${t.name} threw: ${e.message.split('\n')[0]}`);
  }
}
console.log(failures.length ? `\n${failures.length} GazeStage stress check(s) failed` : '\nAll GazeStage stress checks passed');
process.exit(failures.length ? 1 : 0);
