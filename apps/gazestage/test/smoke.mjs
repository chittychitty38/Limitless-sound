// Launches the app with a fake camera and microphone and checks that the face model loads
// offline, the camera and mic open, and the page throws no errors.
// Run with `npm test` (on Linux CI wrap it in xvfb-run).
import { _electron as electron } from 'playwright';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// `--packaged` tests the built app in dist/ instead of the source tree.
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const packaged = process.argv.includes('--packaged');
const BUILT = {
  darwin: join(root, 'dist', process.arch === 'arm64' ? 'mac-arm64' : 'mac', 'GazeStage.app', 'Contents', 'MacOS', 'GazeStage'),
  win32: join(root, 'dist', 'win-unpacked', 'GazeStage.exe'),
  linux: join(root, 'dist', 'linux-unpacked', 'gazestage'),
};
const flags = ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'];
const app = await electron.launch(packaged
  ? { executablePath: BUILT[process.platform], args: flags }
  : { executablePath: createRequire(import.meta.url)('electron'), args: [root, ...flags] });
try {
  const win = await app.firstWindow();
  const errors = [];
  win.on('pageerror', (e) => errors.push(e.message));
  await win.waitForLoadState();
  assert.equal(await win.title(), 'GazeStage');

  await win.click('#startBtn');
  await win.waitForFunction(() => /tracking|no face|could not/.test(document.getElementById('status').textContent), null, { timeout: 60000 });
  const status = await win.textContent('#status');
  assert.doesNotMatch(status, /could not/, status);

  await win.selectOption('#select', 'sound');
  await win.waitForTimeout(1000);
  assert.doesNotMatch(await win.textContent('#last'), /Microphone blocked/);

  await win.click('[data-goto=play]');
  assert.equal(await win.locator('#padgrid .target').count(), 8);
  assert.deepEqual(errors, []);
  console.log('smoke test passed:', status.trim());
} finally {
  await app.close();
}
