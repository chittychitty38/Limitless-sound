// Temporary: what the released GazeStage does with the CPU while it sits idle on a Mac.
//   node gazestage-idle.cjs <GazeStage executable>
const { _electron: electron } = require('playwright');
const { execSync } = require('node:child_process');
const { mkdtempSync } = require('node:fs');
const { join } = require('node:path');
const { tmpdir } = require('node:os');

const exe = process.argv[2];
const wait = (s) => new Promise((r) => setTimeout(r, s * 1000));
const secs = (t) => t.split(/[:-]/).reduce((a, v) => a * 60 + Number(v), 0);   // "1:02.53"

function procs() {
  const out = {};
  for (const line of execSync('ps -axo pid=,time=,command=', { maxBuffer: 1 << 24 }).toString().split('\n')) {
    const m = line.trim().match(/^(\d+)\s+(\S+)\s+(.*)$/);
    if (!m || !m[3].includes('GazeStage.app')) continue;
    const name = m[3].split('/MacOS/')[1]?.split(' --')[0] || m[3];
    const sub = (m[3].match(/--utility-sub-type=(\S+)/) || [])[1] || '';
    out[m[1]] = { cpu: secs(m[2]), name: `${name}${sub ? ' ' + sub : ''}` };
  }
  return out;
}

async function measure(label, seconds = 15) {
  const a = procs(); await wait(seconds); const b = procs();
  let total = 0; const rows = [];
  for (const [pid, p] of Object.entries(b)) {
    const d = (p.cpu - (a[pid]?.cpu ?? p.cpu)) / seconds * 100;
    p.pct = d; total += d; rows.push(`    ${pid.padStart(6)} ${d.toFixed(1).padStart(5)}%  ${p.name}`);
  }
  console.log(`\n== ${label}: ${total.toFixed(1)}% in all`);
  console.log(rows.join('\n'));
  return b;
}

function sample(pids) {
  for (const pid of pids) {
    try {
      execSync(`sample ${pid} 4 -file /tmp/s-${pid}.txt`, { stdio: 'ignore' });
      const top = execSync(`sed -n '/Sort by top of stack/,$p' /tmp/s-${pid}.txt | head -25`).toString();
      const graph = execSync(`sed -n '/Call graph:/,/Total number in stack/p' /tmp/s-${pid}.txt | grep -v "^ *+ *[0-9]* *\\?\\?\\?" | head -70`).toString();
      console.log(`\n-- sample of ${pid}, top of stack:\n${top}\n-- call graph:\n${graph}`);
    } catch (e) { console.log(`sample ${pid} failed: ${e.message}`); }
  }
}

async function metrics(pages, seconds = 10) {
  const sessions = [];
  for (const p of pages) {
    const cdp = await p.context().newCDPSession(p);
    await cdp.send('Performance.enable');
    sessions.push({ p, cdp, a: (await cdp.send('Performance.getMetrics')).metrics });
  }
  await wait(seconds);
  for (const s of sessions) {
    const b = (await s.cdp.send('Performance.getMetrics')).metrics;
    const A = Object.fromEntries(s.a.map((m) => [m.name, m.value]));
    const d = Object.fromEntries(b.filter((m) => /Duration|Count$|Frames/.test(m.name))
      .map((m) => [m.name, +(m.value - (A[m.name] || 0)).toFixed(3)]).filter(([, v]) => v));
    console.log(`  page ${s.p.url()}: ${JSON.stringify(d)}`);
  }
}

(async () => {
  const profile = mkdtempSync(join(tmpdir(), 'gazestage-idle-'));
  const app = await electron.launch({ executablePath: exe, args: [`--user-data-dir=${profile}`] });
  const win = await app.firstWindow();
  console.log('GPU:', JSON.stringify(await app.evaluate(({ app }) => app.getGPUFeatureStatus())));
  console.log('display:', JSON.stringify(await app.evaluate(({ screen }) => screen.getPrimaryDisplay())));
  await wait(20);

  const b = await measure('First launch, guided setup showing (what the proof measures)');
  console.log('\nRenderer work in 10 s:'); await metrics(app.windows());
  sample(Object.keys(b).filter((pid) => b[pid].pct >= 0.3));

  await win.click('[data-ob="skip"]'); await wait(5);
  await measure('Setup skipped, main page showing');
  console.log('\nRenderer work in 10 s:'); await metrics(app.windows());

  const sound = app.windows().find((p) => p.url().endsWith('/synth.html'));
  await sound.evaluate(() => { window.__synth.ensure(); window.__synth.tick(); }); await wait(5);
  const c = await measure('A click played 5 s ago (the built-in instrument\'s audio running)');
  console.log('audio:', JSON.stringify(await sound.evaluate(() => ({ state: window.__synth.ctx.state, rate: window.__synth.ctx.sampleRate, base: window.__synth.ctx.baseLatency, out: window.__synth.ctx.outputLatency }))));
  sample(Object.keys(c).filter((pid) => c[pid].pct >= 0.5));

  await sound.evaluate(() => { const s = window.__synth; s.wet.disconnect(); s.reverb.disconnect(); }); await wait(2);
  await measure('Audio running without the reverb');

  await sound.evaluate(() => window.__synth.ctx.suspend()); await wait(2);
  await measure('Audio suspended');

  await win.evaluate(() => { window.requestAnimationFrame = () => 0; }); await wait(2);
  await measure('Frame loop stopped (requestAnimationFrame does nothing)');

  await win.evaluate(() => { for (let i = 1; i < 100000; i++) clearInterval(i); }); await wait(2);
  await measure('Every timer in the page cleared too (status chips no longer refreshed)');

  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().forEach((w) => w.isVisible() && w.minimize()));
  await wait(3);
  await measure('Window minimised');

  console.log('\nsynth page closed:', await app.evaluate(({ BrowserWindow }) => {
    const s = BrowserWindow.getAllWindows().find((w) => w.webContents.getURL().endsWith('/synth.html'));
    s?.destroy(); return !!s;
  }));
  await wait(3);
  await measure('Synth page closed as well');
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
