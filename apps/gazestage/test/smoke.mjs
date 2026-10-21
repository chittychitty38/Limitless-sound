// Launches the app with a fake camera and microphone and checks that the face model loads
// offline, the camera and mic open, and the page throws no errors.
// Run with `npm test` (on Linux CI wrap it in xvfb-run).
import { _electron as electron } from 'playwright';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const app = await electron.launch({
  executablePath: createRequire(import.meta.url)('electron'),
  args: [root, '--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
});
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
