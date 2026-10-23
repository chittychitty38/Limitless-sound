// Checks every web-based screen in the suite the way the website is checked (axe-core, WCAG 2.2 A
// and AA, light and dark, the usual window size and a small one), in each app's standard, high
// contrast and largest-text looks, and from the keyboard: every control reachable with Tab, in
// document order, with a focus indicator you can see and nothing covering it. Blind and low-vision
// musicians use these screens with VoiceOver; switch and keyboard users see them through the focus.
// Any problem fails.
//
// The screens run the real way where they can:
//   - Limitless Sound's page and Limitless Control's page come from the real hub and the real
//     Control app (in its test mode, which logs key presses instead of making them), joined up.
//   - GazeStage is the real Electron app (Playwright's Electron support, as in its smoke test),
//     joined to the same hub.
//   - The shared text size and high contrast reach those three from the hub's settings API, the
//     way a musician's choice reaches them.
//   - Limitless Color's window is its own page, served with its Tauri CSP, with the Tauri commands
//     and events it uses answered by a small stand-in (the Tauri app builds only on the Mac and
//     Windows runners). Its looks arrive through the same "window-prefs" event the app sends.
//   - The Mac installer's welcome and conclusion pages are plain files, opened as they are.
//
//   xvfb-run -a node .github/scripts/apps-a11y.cjs              every screen (no xvfb-run on a Mac)
//   node .github/scripts/apps-a11y.cjs color installer          some: hub, control, gazestage, color, installer
// Needs playwright 1.56.1 and axe-core 4.10.3 (npm install at the repo root), Python with
// apps/control installed (PYTHON=... picks one), and `npm ci` in apps/gazestage.
const { chromium, _electron } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const zlib = require('zlib');

const ROOT = path.join(__dirname, '..', '..');
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ONLY = process.argv.slice(2);
const wanted = (...names) => !ONLY.length || names.some((n) => ONLY.includes(n));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ls-a11y-'));
const children = [];

// The looks every app takes from Limitless Sound's shared settings.
const LOOKS = {
  standard: { textScale: 1, highContrast: false, reduceMotion: false },
  'high contrast': { textScale: 1, highContrast: true, reduceMotion: false },
  'largest text': { textScale: 2, highContrast: false, reduceMotion: false },
};

// ------------------------------------------------------------------ results
// Each screen keeps its own log (screens run side by side) and a tally for the summary.
const screens = new Map();
function screenOf(name) {
  if (!screens.has(name)) screens.set(name, { name, lines: [], axe: new Map(), keys: new Map(), runs: 0, tabs: 0 });
  return screens.get(name);
}
const flush = (s) => { if (s.lines.length) console.log(s.lines.join('\n')); s.lines = []; };

async function axeCheck(page, s, label) {
  // Evaluated rather than added as a script tag, so a page's CSP (GazeStage allows no inline
  // scripts) doesn't stop it.
  if (!(await page.evaluate(() => !!window.axe))) await page.evaluate(AXE);
  const r = await page.evaluate((tags) => axe.run(document, { runOnly: tags, resultTypes: ['violations'] }), TAGS);
  s.runs++;
  s.lines.push(`  ${label}: ${r.violations.length ? r.violations.length + ' problem(s)' : 'no problems'}`);
  for (const v of r.violations) {
    const e = s.axe.get(v.id) || { states: 0, nodes: 0, help: v.help, impact: v.impact };
    e.states++; e.nodes += v.nodes.length; s.axe.set(v.id, e);
    s.lines.push(`    [${v.impact}] ${v.id}: ${v.help}`);
    for (const n of v.nodes) s.lines.push(`      ${n.target.join(' ')}: ${(n.failureSummary || '').split('\n').slice(1).join(' ').trim()}`);
  }
}

// ------------------------------------------------------------------ keyboard
// A small PNG reader (8-bit RGB or RGBA, as Chromium's screenshots are), to compare a control
// focused and not focused.
function decodePng(buf) {
  let pos = 8, width = 0, height = 0, depth = 0, type = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos), kind = buf.toString('ascii', pos + 4, pos + 8), data = buf.subarray(pos + 8, pos + 8 + len);
    if (kind === 'IHDR') { width = data.readUInt32BE(0); height = data.readUInt32BE(4); depth = data[8]; type = data[9]; if (data[12]) throw new Error('interlaced PNG'); }
    else if (kind === 'IDAT') idat.push(data);
    else if (kind === 'IEND') break;
    pos += 12 + len;
  }
  if (depth !== 8 || (type !== 2 && type !== 6)) throw new Error(`unexpected PNG (type ${type}, depth ${depth})`);
  const bpp = type === 6 ? 4 : 3, stride = width * bpp, raw = zlib.inflateSync(Buffer.concat(idat));
  const out = new Uint8Array(width * height * 3);
  let prev = new Uint8Array(stride), cur = new Uint8Array(stride);
  for (let y = 0; y < height; y++) {
    const f = raw[y * (stride + 1)], line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? cur[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
      let v = line[i];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      cur[i] = v & 255;
    }
    for (let x = 0; x < width; x++) { const o = (y * width + x) * 3, s = x * bpp; out[o] = cur[s]; out[o + 1] = cur[s + 1]; out[o + 2] = cur[s + 2]; }
    [prev, cur] = [cur, prev];
  }
  return { width, height, data: out };
}
// Pixels that clearly changed between a clip and the same place in a whole-window picture.
function changedPixels(clip, img, at) {
  let n = 0;
  for (let y = 0; y < clip.height; y++) {
    for (let x = 0; x < clip.width; x++) {
      const i = (y * clip.width + x) * 3, j = ((y + at.y) * img.width + x + at.x) * 3;
      if (Math.abs(clip.data[i] - img.data[j]) + Math.abs(clip.data[i + 1] - img.data[j + 1]) + Math.abs(clip.data[i + 2] - img.data[j + 2]) >= 60) n++;
    }
  }
  return n;
}

// Installed in the page: names for elements, what the focused element looks like, and what should
// be reachable.
const KB_HELPERS = `(() => {
  if (window.__kb) return;
  const ids = new WeakMap(); let next = 1;
  const id = (el) => { if (!ids.has(el)) ids.set(el, next++); return ids.get(el); };
  const COMPOSITE = new Set(['tab', 'radio', 'option', 'menuitem', 'menuitemradio', 'menuitemcheckbox', 'treeitem', 'gridcell']);
  const SEL = 'a[href], area[href], button, input:not([type=hidden]), select, textarea, summary, iframe, [contenteditable=""], [contenteditable=true], [tabindex], ' +
    '[role=button], [role=link], [role=checkbox], [role=radio], [role=switch], [role=tab], [role=slider], [role=spinbutton], [role=textbox], [role=combobox], [role=menuitem], [role=option]';
  const describe = (el) => {
    const name = (el.getAttribute('aria-label') || el.labels?.[0]?.textContent || el.getAttribute('title') || el.textContent || el.value || el.placeholder || '').replace(/\\s+/g, ' ').trim().slice(0, 50);
    const what = el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.getAttribute('role') ? '[role=' + el.getAttribute('role') + ']' : '') + (el.type && el.tagName === 'INPUT' ? '[type=' + el.type + ']' : '');
    return name ? what + ' "' + name + '"' : what;
  };
  const shown = (el) => {
    if (!el.getClientRects().length) return false;
    for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.display === 'none') return false; }
    return true;
  };
  const layerOk = (el) => {
    if (el.closest('[inert]')) return false;
    const modal = document.querySelector('dialog:modal');
    return !modal || modal.contains(el);
  };
  const groupOf = (el) => {
    const role = el.getAttribute('role') || (el.type === 'radio' ? 'radio' : '');
    if (role === 'radio' && el.name) return 'radio:' + el.name;
    if (role === 'radio' || role === 'tab' || role === 'option') { const g = el.closest('[role=radiogroup], [role=tablist], [role=listbox]'); if (g) return 'group:' + id(g); }
    return null;
  };
  window.__kb = {
    // Everything a keyboard user should be able to reach on the screen as it is now.
    expected() {
      const out = [];
      for (const el of document.querySelectorAll(SEL)) {
        if (el.disabled || !shown(el) || !layerOk(el)) continue;
        const role = el.getAttribute('role') || (el.type === 'radio' ? 'radio' : '');
        if (el.getAttribute('tabindex') === '-1' && !COMPOSITE.has(role)) continue;   // focused by the page itself, not with Tab
        if (el.closest('details:not([open])') && el.tagName !== 'SUMMARY') continue;
        out.push({ key: id(el), group: groupOf(el), desc: describe(el) });
      }
      return out;
    },
    focused() {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return { key: 0 };
      // A visually hidden input (a file input behind a styled label) shows its focus on its label.
      let box = el;
      const own = el.getBoundingClientRect();
      if (own.width <= 2 || own.height <= 2) box = [...(el.labels || [])].find(shown) || el;
      const r = box.getBoundingClientRect(), pad = 12;
      const clip = { x: Math.max(0, Math.floor(r.left - pad)), y: Math.max(0, Math.floor(r.top - pad)) };
      clip.width = Math.min(innerWidth, Math.ceil(r.right + pad)) - clip.x; clip.height = Math.min(innerHeight, Math.ceil(r.bottom + pad)) - clip.y;
      const vis = { l: Math.max(0, r.left), t: Math.max(0, r.top), r: Math.min(innerWidth, r.right), b: Math.min(innerHeight, r.bottom) };
      const onScreen = vis.r - vis.l >= 1 && vis.b - vis.t >= 1 && shown(box);
      let hitOk = false;
      if (onScreen) {
        const hit = document.elementFromPoint((vis.l + vis.r) / 2, (vis.t + vis.b) / 2);
        hitOk = !!hit && (hit === el || el.contains(hit) || [...(el.labels || [])].some((l) => l.contains(hit)));
      }
      // Where everything around it is scrolled to: the same means an earlier picture still fits.
      let scrolled = scrollX + ',' + scrollY;
      for (let e = el.parentElement; e; e = e.parentElement) if (e.scrollTop || e.scrollLeft) scrolled += ';' + id(e) + ':' + e.scrollLeft + ',' + e.scrollTop;
      return { key: id(el), group: groupOf(el), desc: describe(el), clip, onScreen, hitOk, scrolled,
        perimeter: 2 * ((vis.r - vis.l) + (vis.b - vis.t)), tabindex: el.tabIndex };
    },
    // Is b after a in the document?
    after(aKey, bKey) {
      let a = null, b = null;
      for (const el of document.querySelectorAll('*')) { if (ids.get(el) === aKey) a = el; if (ids.get(el) === bKey) b = el; }
      return !!a && !!b && !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    },
    blur() { const el = document.activeElement; window.__kbLast = el; el?.blur(); },
    refocus() { window.__kbLast?.focus({ preventScroll: true }); },
    still(on) {
      // Nothing moving and no text cursor while comparing pictures. (Playwright's own options for
      // this restyle the page on every screenshot, which is slow.)
      document.getElementById('__kb-still')?.remove();
      if (!on) return;
      const st = document.createElement('style'); st.id = '__kb-still';
      st.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }';
      document.head.append(st);
    },
  };
})()`;

// A new look reaches the other apps too, and the hub's page redraws its lists a moment later when
// they report that they've applied it. Tabbing through a list while it's replaced reads as focus
// jumping back and controls that can't be reached (seen in CI on the Links tab, largest text), so
// the hub's checks wait until nothing but its activity log has changed for a while.
async function settled(page, quietMs = 1500, maxMs = 15000) {
  await page.evaluate(([quietMs, maxMs]) => new Promise((resolve) => {
    let timer = 0;
    const cap = setTimeout(() => done(), maxMs);
    const done = () => { obs.disconnect(); clearTimeout(timer); clearTimeout(cap); resolve(); };
    const inLog = (node) => (node.nodeType === 1 ? node : node.parentElement)?.closest('#log, [aria-live]');
    const obs = new MutationObserver((records) => {
      if (records.every((r) => inLog(r.target))) return;
      clearTimeout(timer); timer = setTimeout(done, quietMs);
    });
    obs.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    timer = setTimeout(done, quietMs);
  }), [quietMs, maxMs]);
}

async function keyboardCheck(page, s, label) {
  await page.evaluate(KB_HELPERS);
  const problems = [];
  const problem = (kind, text) => { problems.push(`${kind}: ${text}`); s.keys.set(kind, (s.keys.get(kind) || 0) + 1); };
  const expected = await page.evaluate(() => __kb.expected());
  const seen = [], seenKeys = new Set(), seenGroups = new Set();
  await page.evaluate(() => __kb.still(true));
  let wraps = 0, unfocused = null;   // the window with nothing focused, for where it's scrolled to now
  for (let step = 0; step < Math.max(60, expected.length * 2 + 10); step++) {
    await page.keyboard.press('Tab');
    const f = await page.evaluate(() => __kb.focused());
    if (!f.key) { if (++wraps > 2) break; continue; }   // past the last control, before the first again
    if (seenKeys.has(f.key)) break;
    seenKeys.add(f.key); if (f.group) seenGroups.add(f.group);
    seen.push(f);
    if (f.tabindex > 0) problem('positive tabindex', `${f.desc} has tabindex ${f.tabindex}, which takes it out of the page's order`);
    if (!f.onScreen) { problem('focus off screen', `${f.desc} takes focus but can't be seen`); continue; }
    if (!f.hitOk) problem('focus hidden', `${f.desc} takes focus under something covering it`);
    if (f.clip.width < 1 || f.clip.height < 1) continue;
    if (unfocused?.scrolled !== f.scrolled) {
      await page.evaluate(() => __kb.blur());
      unfocused = { scrolled: f.scrolled, img: decodePng(await page.screenshot({ caret: 'initial' })) };
      await page.evaluate(() => __kb.refocus());
    }
    const changed = changedPixels(decodePng(await page.screenshot({ clip: f.clip, caret: 'initial' })), unfocused.img, f.clip);
    const need = Math.round(Math.max(40, f.perimeter));
    if (changed < need) problem('no visible focus', `${f.desc}: focusing it changes ${changed} pixels (at least ${need} needed, a 1 px ring all round)`);
  }
  await page.evaluate(() => __kb.still(false));
  // Every control reachable (one per radio group or tab list is enough: arrow keys move within it).
  for (const e of expected) {
    if (seenKeys.has(e.key) || (e.group && seenGroups.has(e.group))) continue;
    problem('not reachable', `${e.desc} can't be reached with Tab`);
  }
  // In document order, starting from whichever control comes first.
  if (seen.length > 1) {
    let start = 0;
    for (let i = 1; i < seen.length; i++) if (await page.evaluate(([a, b]) => __kb.after(a, b), [seen[i].key, seen[start].key])) start = i;
    const ring = [...seen.slice(start), ...seen.slice(0, start)];
    for (let i = 1; i < ring.length; i++) {
      if (!(await page.evaluate(([a, b]) => __kb.after(a, b), [ring[i - 1].key, ring[i].key])))
        problem('order', `Tab goes from ${ring[i - 1].desc} back to ${ring[i].desc}`);
    }
  }
  s.tabs++;
  s.lines.push(`  ${label}, keyboard: ${seen.length} stops, ${problems.length ? problems.length + ' problem(s)' : 'no problems'}`);
  for (const p of problems) s.lines.push(`    ${p}`);
}

// ------------------------------------------------------------------ states
// A view of a screen in each look, light and dark, at each size (the usual one first). setLook puts
// the app in a look, setScheme in light or dark. keys says where the keyboard check runs.
const WIDE = 1280;
async function checkStates(page, s, view, { looks = Object.keys(LOOKS), setLook, setScheme, sizes, keys = allKeys, settle }) {
  s.lines.push(`${s.name}: ${view}`);
  for (const look of looks) {
    if (setLook) await setLook(look);
    for (const scheme of ['light', 'dark']) {
      await setScheme(scheme);
      for (const [i, [width, height]] of sizes.entries()) {
        await page.setViewportSize({ width, height });
        await sleep(250);
        // Checked at rest, not halfway through a fade.
        await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), null, { timeout: 3000 }).catch(() => {});
        if (settle) await settle();
        const label = `${look === 'standard' ? '' : look + ', '}${scheme}, ${width} x ${height}`;
        await axeCheck(page, s, label);
        if (keys(look, scheme, i === 0)) await keyboardCheck(page, s, label);
      }
    }
  }
  flush(s);
}
// The focus in each palette and layout without repeating every combination: the standard look in
// light and dark at the usual size and in light at the small one, high contrast in dark, and the
// largest text in light.
function allKeys(look, scheme, usual) {
  if (look === 'standard') return usual || scheme === 'light';
  if (look === 'high contrast') return usual && scheme === 'dark';
  return usual && scheme === 'light';
}
// For a view with the same controls as one checked in full: its usual size, standard and high contrast.
const someKeys = (look, scheme, usual) => usual && ((look === 'standard' && scheme === 'light') || (look === 'high contrast' && scheme === 'dark'));

// ------------------------------------------------------------------ processes
async function freePort() {
  return new Promise((resolve) => { const sv = net.createServer(); sv.listen(0, '127.0.0.1', () => { const p = sv.address().port; sv.close(() => resolve(p)); }); });
}
function start(name, cmd, args, opts) {
  const logFile = path.join(tmp, `${name}.log`);
  const child = spawn(cmd, args, { ...opts, stdio: ['ignore', fs.openSync(logFile, 'w'), fs.openSync(logFile, 'a')] });
  child.on('exit', (code) => { if (code && !child.stopping) console.log(`${name} exited with ${code}:\n${fs.readFileSync(logFile, 'utf8')}`); });
  children.push(child);
  return child;
}
async function waitFor(what, fn, ms = 30000) {
  const end = Date.now() + ms;
  for (;;) {
    try { const v = await fn(); if (v) return v; } catch {}
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await sleep(100);
  }
}
const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));

// ------------------------------------------------------------------ the hub (Limitless Sound)
const hubHome = path.join(tmp, 'hub-home'), logs = path.join(tmp, 'logs');
const opened = new Set();   // apps joined to the hub
let hub = null;   // { http, token }
async function startHub() {
  const port = await freePort(), httpPort = await freePort();
  start('hub', PYTHON, ['-m', 'limitless_hub', '--background', '--port', String(port), '--http-port', String(httpPort)], {
    cwd: path.join(ROOT, 'shared', 'hub'),
    env: { ...process.env, LIMITLESS_SOUND_HOME: hubHome, LIMITLESS_SOUND_LOGS: logs },
  });
  const link = await waitFor('the hub', () => fs.existsSync(path.join(hubHome, 'link.json')) && readJson(path.join(hubHome, 'link.json')));
  hub = { http: link.http, token: link.token };
}
async function hubApi(p, body) {
  const r = await fetch(`http://127.0.0.1:${hub.http}${p}`, {
    method: body === undefined ? 'GET' : 'POST', body: body === undefined ? undefined : JSON.stringify(body),
    headers: { 'X-Limitless-Token': hub.token, 'Content-Type': 'application/json' },
  });
  return r.json();
}
// Sets the shared look in Limitless Sound and waits until each open app says it uses it.
async function sharedLook(look) {
  const want = LOOKS[look];
  await hubApi('/api/prefs', { prefs: want });
  await waitFor(`${[...opened].join(', ')} to use the ${look} look`, async () => {
    const st = await hubApi('/api/state');
    return [...opened].every((a) => {
      const got = st.states[`${a}.prefs.applied`];
      return got && got.highContrast === want.highContrast && Math.abs(got.textScale - want.textScale) < 0.01;
    });
  }, 10000);
}
const joined = async (tool) => (await hubApi('/api/state')).tools.find((t) => t.id === tool)?.connected;

async function checkHub(browser) {
  const s = screenOf('Limitless Sound (hub page)');
  const ctx = await browser.newContext({ viewport: { width: WIDE, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${hub.http}/?t=${hub.token}`);
  await page.waitForSelector('#setup:not([hidden])');
  const setScheme = (colorScheme) => page.emulateMedia({ colorScheme });
  const sizes = [[WIDE, 900], [390, 844]];

  // The guided setup shows the text size and contrast picked in it at once: its looks come from there.
  await checkStates(page, s, 'guided setup (first launch)', {
    sizes, setScheme,
    setLook: async (look) => {
      await page.selectOption('#setup-size', String(LOOKS[look].textScale));
      await page.setChecked('#setup-contrast', LOOKS[look].highContrast);
      await sleep(100);
    },
  });
  await page.setChecked('#setup-contrast', false);
  await page.selectOption('#setup-size', '1');
  await page.click('#setup-skip');
  await page.waitForSelector('#setup[hidden]', { state: 'attached' });

  const setLook = async (name) => {
    await sharedLook(name);
    await page.waitForFunction(([hc, ts]) => document.documentElement.hasAttribute('data-contrast') === hc
      && Number(getComputedStyle(document.documentElement).getPropertyValue('--scale')) === ts, [LOOKS[name].highContrast, LOOKS[name].textScale]);
    await settled(page);
  };
  for (const [tab, name] of [['t-tools', 'My apps'], ['t-do', 'Do anything'], ['t-links', 'Links'], ['t-settings', 'Settings'], ['t-activity', 'Activity']]) {
    await page.click('#' + tab);
    await settled(page);
    await checkStates(page, s, name, { sizes, setScheme, setLook });
  }
  await sharedLook('standard');

  // The page in Spanish: longer words in the same space, and the page's language set for screen
  // readers. The guided setup, then the tabs with the most words.
  await hubApi('/api/prefs', { prefs: { language: 'es' } });
  await page.waitForFunction(() => document.documentElement.lang === 'es');
  await page.click('#t-tools');
  await page.click('#setup-again');
  await page.waitForSelector('#setup:not([hidden])');
  await checkStates(page, s, 'guided setup, in Spanish', { looks: ['standard', 'largest text'], sizes, setScheme,
    setLook: async (look) => { await page.selectOption('#setup-size', String(LOOKS[look].textScale)); await sleep(100); } });
  await page.selectOption('#setup-size', '1');
  await page.click('#setup-skip');
  await page.waitForSelector('#setup[hidden]', { state: 'attached' });
  for (const [tab, name] of [['t-tools', 'My apps'], ['t-settings', 'Settings']]) {
    await page.click('#' + tab);
    await settled(page);
    await checkStates(page, s, `${name}, in Spanish`, { looks: ['standard', 'largest text'], sizes, setScheme, setLook });
  }
  await sharedLook('standard');
  await hubApi('/api/prefs', { prefs: { language: 'en' } });
  await ctx.close();
}

// ------------------------------------------------------------------ Limitless Control
let control = null;   // { port, token }
async function startControl() {
  const xdg = path.join(tmp, 'control-config');
  start('control', PYTHON, ['-m', 'limitless_control', '--test-mode', '--background'], {
    cwd: path.join(ROOT, 'apps', 'control'),
    env: {
      ...process.env, LIMITLESS_SOUND_HOME: hubHome, LIMITLESS_SOUND_LOGS: logs, XDG_CONFIG_HOME: xdg,
      LIMITLESS_CONFIG: path.join(xdg, 'settings.json'), SDL_VIDEODRIVER: 'dummy', SDL_AUDIODRIVER: 'dummy',
      BROWSER: 'true',   // the first launch opens its page in a browser: not here
    },
  });
  const session = path.join(xdg, 'Limitless Control', 'session.json');
  control = await waitFor('Limitless Control', () => fs.existsSync(session) && readJson(session));
  await waitFor('Limitless Control to join Limitless Sound', () => joined('control'));
  opened.add('control');
}

async function checkControl(browser) {
  const s = screenOf('Limitless Control (settings page)');
  const ctx = await browser.newContext({ viewport: { width: WIDE, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${control.port}/?t=${control.token}`);
  await page.waitForSelector('#setup:not([hidden])');
  await page.waitForSelector('#rows tr');
  const setScheme = (colorScheme) => page.emulateMedia({ colorScheme });
  const setLook = async (name) => {
    await sharedLook(name);
    await page.waitForFunction(([hc, ts]) => document.documentElement.classList.contains('high-contrast') === hc
      && Number(document.documentElement.style.getPropertyValue('--scale') || 1) === ts, [LOOKS[name].highContrast, LOOKS[name].textScale]);
  };
  const sizes = [[WIDE, 900], [390, 844]];
  await checkStates(page, s, 'first launch: welcome steps', { sizes, setScheme, setLook });

  // Welcome steps done, a switch held down (its row and button light up) and the activity log open.
  await page.click('#setup-done');
  await page.waitForSelector('#setup[hidden]', { state: 'attached' });
  const simulate = (input, down) => page.evaluate(async ([i, d]) => {
    await fetch('/api/simulate', { method: 'POST', headers: { 'X-Token': sessionStorage.getItem('lc-token'), 'Content-Type': 'application/json' }, body: JSON.stringify({ input: i, down: d }) });
  }, [input, down]);
  await simulate('a', true);
  await page.waitForSelector('#row-a.hit');
  await page.waitForSelector('#pad .btn.down');
  await page.click('details summary');
  await checkStates(page, s, 'playing: a switch held, activity log open', { sizes, setScheme, setLook, keys: someKeys });
  await simulate('a', false);

  // Logic Pro's layer 2 with a custom key command being typed, then the switches for every app.
  await page.selectOption('#profile-pick', 'Logic Pro');
  await page.check('input[name=layer][value="1"]');
  await page.selectOption('#row-x select', 'custom');
  await page.waitForSelector('#row-x input.custom:not([hidden])');
  await checkStates(page, s, 'Logic Pro, layer 2, a custom key command', { sizes, setScheme, setLook, keys: someKeys });
  await page.selectOption('#row-x select', '');
  await page.check('input[name=layer][value="0"]');
  await page.selectOption('#profile-pick', '__global__');
  await checkStates(page, s, 'every app (always on)', { sizes, setScheme, setLook, looks: ['standard'], keys: someKeys });
  await sharedLook('standard');

  // The page in Spanish: longer words in the same space, and the page's language set for screen
  // readers. The welcome steps shown again above Logic Pro's switches: every part of the page.
  await hubApi('/api/prefs', { prefs: { language: 'es' } });
  await page.waitForFunction(() => document.documentElement.lang === 'es');
  await page.selectOption('#profile-pick', 'Logic Pro');
  await page.click('#show-setup');
  await page.waitForSelector('#setup:not([hidden])');
  await checkStates(page, s, 'welcome steps and Logic Pro, in Spanish', { looks: ['standard', 'largest text'], sizes, setScheme, setLook });
  await sharedLook('standard');
  await hubApi('/api/prefs', { prefs: { language: 'en' } });
  await ctx.close();
}

// ------------------------------------------------------------------ GazeStage
let gaze = null;   // { app, win }
async function startGazeStage() {
  const dir = path.join(ROOT, 'apps', 'gazestage');
  const app = await _electron.launch({
    executablePath: require(path.join(dir, 'node_modules', 'electron')),
    args: [dir, '--no-sandbox', `--user-data-dir=${path.join(tmp, 'gazestage-profile')}`],
    env: { ...process.env, LIMITLESS_SOUND_HOME: hubHome, LIMITLESS_SOUND_LOGS: logs },
  });
  const win = await app.firstWindow();
  await win.waitForLoadState();
  gaze = { app, win };
  await waitFor('GazeStage to join Limitless Sound', () => joined('gaze'));
  opened.add('gaze');
}

async function checkGazeStage() {
  const s = screenOf('GazeStage (window)');
  const { win } = gaze;
  // Its own Appearance setting (dark unless chosen otherwise), as picked in its Settings.
  const setScheme = (theme) => win.evaluate((t) => { const el = document.getElementById('sTheme'); el.value = t; el.dispatchEvent(new Event('change')); }, theme);
  const setLook = async (name) => {
    await sharedLook(name);
    await win.waitForFunction(([hc, ts]) => document.documentElement.dataset.contrast === (hc ? 'high' : 'normal')
      && Number(document.documentElement.style.getPropertyValue('--scale')) === ts, [LOOKS[name].highContrast, LOOKS[name].textScale]);
  };
  // Its usual size (1280 x 800 or the screen) and its smallest (760 x 560), once any message it
  // shows for a moment has gone.
  const settle = () => win.waitForFunction(() => !document.getElementById('toast').classList.contains('show'), null, { timeout: 8000 });
  const states = (view, more = {}) => checkStates(win, s, view, { sizes: [[WIDE, 800], [760, 560]], setScheme, setLook, settle, ...more });
  // Pressed the way Enter or a switch presses a target. The mouse waits in a corner, where
  // dwelling selects nothing (moved there anew: a move to where it already is may not count).
  const park = async () => { await win.mouse.move(4, 4); await win.mouse.move(2, 2); };
  const press = async (sel) => { await win.evaluate((q) => document.querySelector(q).click(), sel); await park(); await sleep(200); };
  await win.setViewportSize({ width: WIDE, height: 800 });
  await win.waitForSelector('#onboard.show');
  await park();

  await states('guided setup: welcome');
  await press('[data-ob=next]');
  await states('guided setup: camera');
  // A mouse instead (the camera would need a face in front of it), and a switch to select: then
  // nothing is selected by the pointer resting somewhere while the keyboard is checked.
  await press('[data-ob=nocam]');
  await press('[data-ob=select][data-value=switch]');
  await states('guided setup: how to select');
  await press('[data-ob=back]');
  await states('guided setup: how to point');
  await press('[data-ob=next]');
  await press('[data-ob=next]');
  await states('guided setup: try it');
  await press('[data-ob=next]');
  await states('guided setup: ready');
  await press('[data-ob=finish-play]');
  await win.waitForSelector('#onboard:not(.show)', { state: 'attached' });
  await states('instrument');
  await press('[data-goto=transport]');
  await states('transport');
  await press('[data-goto=tone]');
  await states('tone pad');
  await win.evaluate(() => document.getElementById('settingsBtn').click());
  await win.waitForSelector('#settings.open');
  await sleep(300);
  await states('settings');
  const profile = (v) => win.evaluate((x) => { const el = document.getElementById('sXyProfile'); el.value = x; el.dispatchEvent(new Event('change')); }, v);
  await profile('custom');   // the tone pad's own controller numbers
  await states('settings: the tone pad on chosen controller numbers', { looks: ['standard', 'high contrast'], keys: someKeys });
  await profile('learn');
  await win.evaluate(() => document.getElementById('closeSettings').click());
  await sleep(300);
  await press('[data-action=pause]');
  await win.waitForSelector('#pauseOverlay.show');
  await states('paused', { keys: someKeys });
  await press('#pauseOverlay [data-action=resume]');
  await sharedLook('standard');

  // GazeStage in Spanish: longer words on the same targets, and the window's language set for
  // screen readers. The guided setup's busiest step, the three pages and the settings.
  await hubApi('/api/prefs', { prefs: { language: 'es' } });
  await win.waitForFunction(() => document.documentElement.lang === 'es');
  const spanish = (view, more = {}) => states(`${view}, in Spanish`, { looks: ['standard', 'largest text'], ...more });
  await win.evaluate(() => document.getElementById('settingsBtn').click());
  await win.waitForSelector('#settings.open');
  await sleep(300);
  await spanish('settings');
  await press('[data-cmd=onboarding]');
  await win.waitForSelector('#onboard.show');
  await press('[data-ob=next]');
  await press('[data-ob=nocam]');
  await spanish('guided setup: how to select');
  await press('[data-ob=next]');
  await press('[data-ob=next]');
  await press('[data-ob=finish-play]');
  await win.waitForSelector('#onboard:not(.show)', { state: 'attached' });
  await spanish('instrument');
  await press('[data-goto=transport]');
  await spanish('transport');
  await press('[data-goto=tone]');
  await spanish('tone pad');
  await sharedLook('standard');
  await hubApi('/api/prefs', { prefs: { language: 'en' } });
}

// ------------------------------------------------------------------ Limitless Color
// Answers the Tauri commands and events the window uses, like the app on a Mac (so the setup has
// its screen-recording step). Screen access starts off, so the setup shows how to turn it on.
const COLOR_STUB = `(() => {
  const DEFAULTS = { type: 'deutan', severity: 0.8, daltonize: 0, rgSplit: 0, bySplit: 0, redShift: 0, greenShift: 0, yellowShift: 0, blueShift: 0, saturation: 1, contrast: 1, focus: 0.08 };
  const listeners = {};
  const status = { profile: { S: { ...DEFAULTS }, anchors: {} }, filterOn: false, filterKind: 'overlay', filterNote: '', platform: 'mac',
    hasApiKey: false, shortcut: 'CommandOrControl+Alt+C', onboarding: '', autostart: false,
    windowPrefs: { textScale: 1, highContrast: false, reduceMotion: false } };
  const copy = () => JSON.parse(JSON.stringify(status));
  const pairs = [['record', 'play', 'Record vs Play'], ['solo', 'mute', 'Solo vs Mute'], ['meterLow', 'meterClip', 'Meter: safe vs clipping'], ['meterLow', 'meterMid', 'Meter: safe vs hot'],
    ['meterMid', 'meterClip', 'Meter: hot vs clipping'], ['record', 'input', 'Record vs Input'], ['tKick', 'tKeys', 'Red track vs green track'], ['tVox', 'tBgv', 'Blue track vs purple track'], ['tGtr', 'tVox', 'Teal track vs blue track']];
  const commands = {
    get_status: () => copy(),
    set_profile: ({ profile }) => { status.profile = profile; },
    set_filter: ({ on }) => { status.filterOn = on; status.filterNote = on ? 'Your colors are on everywhere.' : ''; return copy(); },
    set_onboarding: ({ step }) => { status.onboarding = step; return copy(); },
    restart_filter: () => copy(),
    set_autostart: ({ on }) => { status.autostart = on; return copy(); },
    set_system_motion: () => {},
    auto_tune_profile: ({ cvd, severity }) => ({
      profile: { S: { ...DEFAULTS, type: cvd, severity, daltonize: 0.6, redShift: -20, greenShift: 22, rgSplit: 0.2 }, anchors: {} },
      pairs: pairs.map(([a, b, label], i) => ({ a, b, label, before: 0.04, after: i < 7 ? 0.15 : 0.08 })), pinned: [] }),
    screen_permission: () => 'denied',
    open_screen_settings: () => {}, relaunch: () => {}, start_dictation: () => {}, set_api_key: () => {},
    export_cube: () => '/Users/musician/Documents/Limitless Color/limitless-color.cube',
    ask_assistant: () => ({ reply: 'I moved reds toward pink and greens toward blue-green.', question: 'Do Record and Play look different now?',
      changes: ['Move reds: -20°', 'Move greens: +22°'], note: '', status: copy() }),
  };
  window.__TAURI__ = {
    core: { invoke: async (cmd, args = {}) => { if (!(cmd in commands)) throw new Error('no command ' + cmd); return commands[cmd](args); } },
    event: { listen: async (name, fn) => { (listeners[name] ||= []).push(fn); return () => {}; } },
  };
  // What the app sends the window: its status, and the window's text size, contrast and motion.
  window.__colorApp = { emit: (name, payload) => (listeners[name] || []).forEach((fn) => fn({ payload })) };
})()`;

async function serveColor() {
  const dir = path.join(ROOT, 'apps', 'color', 'app', 'ui');
  const csp = readJson(path.join(ROOT, 'apps', 'color', 'app', 'src-tauri', 'tauri.conf.json')).app.security.csp;
  const types = { '.html': 'text/html; charset=utf-8', '.woff2': 'font/woff2', '.txt': 'text/plain' };
  const server = http.createServer((req, res) => {
    const file = path.join(dir, decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/$/, '/index.html'));
    if (!file.startsWith(dir + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Content-Security-Policy': csp });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  return server;
}

async function checkColor(browser) {
  const s = screenOf('Limitless Color (window)');
  const server = await serveColor();
  const ctx = await browser.newContext({ viewport: { width: WIDE, height: 900 } });
  await ctx.addInitScript(COLOR_STUB);
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForSelector('dialog#setup[open]');
  const setScheme = (colorScheme) => page.emulateMedia({ colorScheme });
  const setLook = (name) => page.evaluate((p) => window.__colorApp.emit('window-prefs', p), LOOKS[name]);
  // The window as it opens (1280 x 900) and at its smallest (420 x 600).
  const states = (view, more = {}) => checkStates(page, s, view, { sizes: [[WIDE, 900], [420, 600]], setScheme, setLook, ...more });
  const click = async (text) => { await page.locator('#setupBody button', { hasText: text }).first().click(); await sleep(150); };

  await states('setup: welcome');
  await click("Let's start");
  await states('setup: eye check');
  await click('Start the check');
  await states('setup: eye check, a pair');
  for (let i = 0; i < 6; i++) await click(i % 2 ? 'Clearly different' : 'Same color');
  await states('setup: eye check result');
  await click("That's not right, let me choose");
  await states('setup: choose my color vision');
  await click('Continue');
  await page.waitForSelector('#setupBody canvas');
  await states('setup: colors tuned');
  await click('Yes, use this');
  await page.waitForSelector('#setupBody details');
  await states('setup: screen access');
  await click('Skip for now');
  await states('setup: switch on');
  await click('Switch on screen colors');
  await page.waitForSelector('#setupBody .choice');
  await states('setup: colors on');
  await click('Finish');
  await page.waitForSelector('dialog#setup:not([open])', { state: 'attached' });

  // The window itself: colors on, a conversation with the assistant, the eye check under way and
  // the Claude key box open.
  await page.fill('#ask', 'Solo and mute look the same');
  await page.click('#send');
  await page.waitForSelector('.msg.you');
  await page.locator('#checkBody button', { hasText: 'Start the check' }).click();
  await page.waitForSelector('#checkBody .check-pair');
  await page.click('#claudeBox summary');
  await states('tuner, colors on');
  await ctx.close();
  server.close();
}

// ------------------------------------------------------------------ the Mac installer
async function checkInstaller(browser) {
  const s = screenOf('Mac installer (welcome and conclusion)');
  // Installer.app shows them in a pane about 620 px wide, in the Mac's light or dark appearance,
  // with no text size or contrast setting of its own.
  // Installer shows the English pages, or the Spanish ones on a Mac set to Spanish.
  for (const name of ['en.lproj/welcome', 'en.lproj/conclusion', 'es.lproj/welcome', 'es.lproj/conclusion']) {
    const ctx = await browser.newContext({ viewport: { width: 620, height: 420 } });
    const page = await ctx.newPage();
    await page.goto('file://' + path.join(ROOT, 'packaging', 'mac', 'installer', 'resources', `${name}.html`));
    await checkStates(page, s, `${name}.html`, {
      sizes: [[620, 420], [390, 844]], looks: ['standard'], setScheme: (colorScheme) => page.emulateMedia({ colorScheme }),
      keys: (look, scheme, usual) => usual,
    });
    await ctx.close();
  }
}

// ------------------------------------------------------------------ run
(async () => {
  let failed = false;
  const browser = await chromium.launch();
  const fail = (e) => { console.error(e); failed = true; };
  try {
    await Promise.all([
      // Limitless Sound, Control and GazeStage share the hub, and so its looks: one after another.
      (async () => {
        if (!wanted('hub', 'control', 'gazestage')) return;
        await startHub();
        if (wanted('hub', 'control')) await startControl();
        if (wanted('hub', 'gazestage')) await startGazeStage();
        if (wanted('hub')) await checkHub(browser);
        if (wanted('control')) await checkControl(browser);
        if (wanted('gazestage')) await checkGazeStage();
      })().catch(fail),
      // The others meanwhile.
      (async () => {
        if (wanted('color')) await checkColor(browser);
        if (wanted('installer')) await checkInstaller(browser);
      })().catch(fail),
    ]);
  } finally {
    for (const sc of screens.values()) flush(sc);
    await gaze?.app.close().catch(() => {});
    await browser.close();
    for (const c of children) c.stopping = true;
    // Quit the way the pages' own Quit buttons do, then make sure.
    if (control) await fetch(`http://127.0.0.1:${control.port}/api/quit`, { method: 'POST', headers: { 'X-Token': control.token }, body: '{}' }).catch(() => {});
    if (hub) await hubApi('/api/quit', {}).catch(() => {});
    await sleep(1000);
    for (const c of children) if (c.exitCode === null) c.kill('SIGKILL');
  }
  console.log('\nSummary');
  for (const sc of screens.values()) {
    const axeCount = [...sc.axe.values()].reduce((n, e) => n + e.states, 0), keyCount = [...sc.keys.values()].reduce((n, c) => n + c, 0);
    if (axeCount || keyCount) failed = true;
    console.log(`  ${sc.name}: ${sc.runs} axe checks, ${sc.tabs} keyboard checks, ${axeCount || keyCount ? 'problems' : 'no problems'}`);
    for (const [id, e] of sc.axe) console.log(`    axe ${id} [${e.impact}]: in ${e.states} of ${sc.runs} checks, ${e.nodes} element(s) in all. ${e.help}`);
    for (const [kind, n] of sc.keys) console.log(`    keyboard, ${kind}: ${n}`);
  }
  if (failed && process.env.A11Y_LOGS) for (const f of fs.readdirSync(tmp).filter((f) => f.endsWith('.log'))) console.log(`--- ${f}\n${fs.readFileSync(path.join(tmp, f), 'utf8')}`);
  fs.rmSync(tmp, { recursive: true, force: true });
  process.exit(failed ? 1 : 0);
})();
