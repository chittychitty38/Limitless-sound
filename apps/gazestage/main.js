// GazeStage desktop shell.
// - Serves the renderer from app:// so the camera, microphone and Web MIDI work the same on
//   every platform, fully offline.
// - On macOS (and Linux) creates its own virtual MIDI ports, so Pro Tools and any instrument
//   see "GazeStage" with no IAC or loopback setup. Windows falls back to Web MIDI in the page.
// - Builds the native menu, remembers the window, and asks for camera/mic access when the
//   guided setup reaches that step.
// - Plays the built-in instrument in a hidden page of its own, so starting the computer's audio
//   never holds up the window.
const {
  app, BrowserWindow, Menu, protocol, net, session, systemPreferences, ipcMain, shell, screen, dialog, MessageChannelMain,
} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { Link } = require('./limitless-link');
const applog = require('./applog');

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);
app.setName('GazeStage');
// GazeStage.log in the suite's log folder: what went wrong, when nobody was watching a console.
const log = applog.start('GazeStage', app.getVersion());

const ROOT = path.join(__dirname, 'renderer');
const ALLOWED = new Set(['media', 'midi', 'midiSysex']);
const isMac = process.platform === 'darwin';
const testMode = app.commandLine.hasSwitch('use-fake-device-for-media-stream');
let win = null, quitting = false;

// ---------- virtual MIDI ports ----------
// Port names other apps will see. Pro Tools: Setup > Peripherals > MIDI Controllers > HUI,
// receive from and send to "GazeStage HUI". Instrument tracks: input "GazeStage Notes".
const PORTS = { notes: 'GazeStage Notes', hui: 'GazeStage HUI' };
const midi = { native: false, error: null, out: {}, huiIn: null };

function openVirtualPorts() {
  if (process.platform === 'win32') { midi.error = 'Windows has no virtual MIDI ports; using loopback ports instead'; return; }
  try {
    const { Input, Output } = require('@julusian/midi');
    midi.out.notes = new Output(); midi.out.notes.openVirtualPort(PORTS.notes);
    midi.out.hui = new Output(); midi.out.hui.openVirtualPort(PORTS.hui);
    midi.huiIn = new Input(); midi.huiIn.ignoreTypes(true, true, true);
    midi.huiIn.on('message', (_dt, bytes) => win?.webContents.send('midi:hui-in', bytes));
    midi.huiIn.openVirtualPort(PORTS.hui);
    midi.native = true;
  } catch (e) {
    midi.native = false; midi.error = String(e.message || e);
    log.warn('No virtual MIDI ports:', midi.error);
    closeVirtualPorts();
  }
}
function closeVirtualPorts() {
  for (const p of [midi.out.notes, midi.out.hui, midi.out.tone, midi.huiIn]) { try { p?.closePort(); } catch {} }
  midi.out = {}; midi.huiIn = null;
}

ipcMain.handle('midi:status', () => ({ native: midi.native, ports: PORTS, error: midi.error }));
ipcMain.on('midi:send', (_e, port, bytes) => {
  const o = midi.out[port];
  if (!o || !Array.isArray(bytes)) return;
  // Split a run of complete messages (e.g. a HUI zone + port pair) into single sends.
  try {
    for (let i = 0; i < bytes.length;) {
      const len = (bytes[i] & 0xf0) === 0xc0 || (bytes[i] & 0xf0) === 0xd0 ? 2 : 3;
      o.sendMessage(bytes.slice(i, i + len)); i += len;
    }
  } catch {}   // a device unplugged mid-send; the page re-picks its outputs on its own
});

// Hardware MIDI outputs (a Line 6 Helix over USB, an interface's MIDI out), for the tone pad.
// Our own virtual ports are left out of the list.
// Listed through the notes port GazeStage already has open: any output can list them all.
// Making a new MIDI output for each look (at start, then every 4 s) set up a CoreMIDI client
// every time, which held up this process (the first face came about a second later on an
// Intel Mac) and never gave the clients back.
function hardwareOutputs() {
  const o = midi.out.notes;
  if (!midi.native || !o) return [];
  try {
    const names = [];
    for (let i = 0; i < o.getPortCount(); i++) names.push(o.getPortName(i));
    return [...new Set(names)].filter((n) => n && !/^GazeStage /.test(n) && !/IAC Driver|Midi Through/i.test(n));
  } catch { return []; }
}
ipcMain.handle('midi:outputs', () => hardwareOutputs());
// Open one hardware output as the "tone" port (or close it with an empty name).
ipcMain.handle('midi:open-tone', (_e, name) => {
  try { midi.out.tone?.closePort(); } catch {}
  delete midi.out.tone;
  if (!name || !midi.native) return { ok: !name };
  try {
    const { Output } = require('@julusian/midi');
    const o = new Output();
    for (let i = 0; i < o.getPortCount(); i++) {
      if (o.getPortName(i) === name) { o.openPort(i); midi.out.tone = o; return { ok: true }; }
    }
    return { ok: false, error: `${name} isn't connected` };
  } catch (e) { return { ok: false, error: String(e.message || e) }; }
});

// ---------- Limitless Sound ----------
// Joins the suite hub when it runs: Voice, the controller or a Stream Deck can drive
// GazeStage, and GazeStage's transport presses tell the other apps (the take guard).
const SUITE_ACTIONS = [
  { id: 'play', label: 'Play (Pro Tools link)', intent: 'daw.play' },
  { id: 'stop', label: 'Stop (Pro Tools link)', intent: 'daw.stop' },
  { id: 'record', label: 'Record (Pro Tools link)', intent: 'daw.record' },
  { id: 'pads', label: 'Show the note pads' },
  { id: 'transport', label: 'Show the transport page' },
  { id: 'octaveUp', label: 'Octave up' },
  { id: 'octaveDown', label: 'Octave down' },
  { id: 'scale', label: 'Next scale' },
  { id: 'latch', label: 'Hold notes on or off' },
  { id: 'panic', label: 'All notes off' },
  // The XY tone pad: two MIDI controllers from one point, for a Helix or any plugin.
  { id: 'tone', label: 'Show the tone pad', phrases: ['tone pad', 'show tone'] },
  { id: 'xy.set', label: 'Move the tone pad to a point', args: { x: 'number', y: 'number', glide: 'number' } },
  { id: 'xy.snapA', label: 'Tone pad: go to A', phrases: ['tone A', 'snapshot A'] },
  { id: 'xy.snapB', label: 'Tone pad: go to B', phrases: ['tone B', 'snapshot B'] },
  { id: 'xy.snapC', label: 'Tone pad: go to C', phrases: ['tone C', 'snapshot C'] },
  { id: 'xy.snapD', label: 'Tone pad: go to D', phrases: ['tone D', 'snapshot D'] },
  { id: 'xy.center', label: 'Tone pad: back to the middle', phrases: ['tone center', 'tone middle'] },
  { id: 'xy.left', label: 'Tone pad: step left' },
  { id: 'xy.right', label: 'Tone pad: step right' },
  { id: 'xy.up', label: 'Tone pad: step up' },
  { id: 'xy.down', label: 'Tone pad: step down' },
  { id: 'xy.follow', label: 'Tone pad: follow the pointer on or off' },
];
const TRANSPORT = new Set(['play', 'stop', 'record']);
const suite = { link: null, ids: 1, waiting: new Map(), ready: false, queue: [], tracking: '' };

// Actions from other apps are done by the page. While it loads (or reloads) they wait here
// instead of getting lost; one that still waits after 2.5 s says so, and is never done late.
function askPage(action, args, source) {
  if (!win) return [false, 'GazeStage has no window open.'];
  return new Promise((resolve) => {
    const id = suite.ids++, req = { id, action, args, source };
    const timer = setTimeout(() => {
      suite.waiting.delete(id);
      const queued = suite.queue.indexOf(req);
      if (queued >= 0) suite.queue.splice(queued, 1);
      resolve([false, queued >= 0 ? 'GazeStage is still starting. Try again in a moment.' : 'GazeStage didn’t answer.']);
    }, 2500);
    suite.waiting.set(id, (r) => { clearTimeout(timer); resolve([!!r?.ok, String(r?.message || '')]); });
    if (suite.ready) win.webContents.send('suite:invoke', req); else suite.queue.push(req);
  });
}

function startSuite() {
  suite.link = new Link({
    tool: 'gaze', name: 'GazeStage', version: app.getVersion(), actions: SUITE_ACTIONS, subscribe: [],
    onInvoke: async (action, args, source) => {
      const r = await askPage(action, args, source);
      if (r[0] && TRANSPORT.has(action)) suite.link.did(action);
      return r;
    },
  });
  suite.link.on('connected', (on) => win?.webContents.send('suite:connected', on));
  // The musician's shared settings: the page applies text size, contrast and motion.
  suite.link.on('prefs', (prefs) => win?.webContents.send('suite:prefs', prefs));
  suite.link.start();
  // Which face tracking runs here (media:tracking), told again after every reconnect.
  suite.link.on('connected', (on) => { if (on && suite.tracking) suite.link.state('faceTracking', suite.tracking); });
}

ipcMain.on('suite:result', (_e, id, result) => {
  const done = suite.waiting.get(id);
  if (done) { suite.waiting.delete(id); done(result); }
});
// The page now listens for actions (preload.js). The first time, join Limitless Sound, so other
// apps only see GazeStage once it can answer; after a reload, pass on what waited meanwhile.
ipcMain.on('suite:ready', (e) => {
  if (e.sender !== win?.webContents) return;
  suite.ready = true;
  if (!suite.link) startSuite();
  for (const req of suite.queue.splice(0)) win.webContents.send('suite:invoke', req);
});
ipcMain.on('suite:did', (_e, action) => { if (TRANSPORT.has(action)) suite.link?.did(action); });
ipcMain.handle('suite:invoke', (_e, action, args) => suite.link
  ? suite.link.invoke(String(action), args && typeof args === 'object' ? args : {})
  : { ok: false, message: 'Limitless Sound isn’t running.' });
ipcMain.handle('suite:status', () => ({ connected: !!suite.link?.connected, prefs: suite.link?.connected ? suite.link.prefs : null }));
// What the page is now showing, so the settings page (and the Access Standard test) can see it.
ipcMain.on('suite:applied', (_e, applied) => { if (applied && typeof applied === 'object') suite.link?.state('prefs.applied', applied); });

// ---------- the built-in instrument ----------
// It plays in a hidden page of its own (renderer/synth.html), in a process of its own. Making an
// audio context holds up the page that makes it until the computer's audio device answers, and
// Chromium waits for that twice, up to 10 s each time: on a Mac with no working sound output the
// window froze for 20 s at the first note or transport click, and every action other apps
// pressed meanwhile went unanswered. Here that can only hold up the sound. The window and the
// instrument talk directly, through a MessagePort (renderer/synth-link.js).
let synthWin = null, synthRestarts = 0;
function synthWindow() {
  if (synthWin && !synthWin.isDestroyed()) return synthWin;
  const sw = synthWin = new BrowserWindow({
    show: false, width: 200, height: 200, skipTaskbar: true, focusable: false, title: 'GazeStage sound',
    // Never throttled or lowered in priority for being hidden, so notes start on time.
    webPreferences: { preload: path.join(__dirname, 'synth-preload.js'), contextIsolation: true, sandbox: true, backgroundThrottling: false },
  });
  sw.webContents.on('console-message', pageMessage);
  sw.webContents.on('render-process-gone', (_e, d) => {
    log.error(`The built-in sound stopped: ${d.reason}, exit code ${d.exitCode}`);
    setImmediate(() => {
      if (!sw.isDestroyed()) sw.destroy();
      if (!quitting && win && synthRestarts++ < 3) connectSynth();   // a fresh one
    });
  });
  sw.on('closed', () => { if (synthWin === sw) synthWin = null; });
  // A host of its own (app://synth), so it is never put in the window's process.
  sw.loadURL('app://synth/synth.html');
  return sw;
}
// A new channel between the window and the instrument: when the page starts (or reloads), and
// after the instrument's page is replaced.
function connectSynth() {
  if (!win) return;
  const sw = synthWindow(), { port1, port2 } = new MessageChannelMain();
  win.webContents.postMessage('synth:port', null, [port1]);
  const give = () => { if (!sw.isDestroyed()) sw.webContents.postMessage('synth:port', null, [port2]); };
  if (sw.webContents.isLoading()) sw.webContents.once('did-finish-load', give); else give();
}
ipcMain.on('synth:connect', (e) => { if (e.sender === win?.webContents) connectSynth(); });

// A question for the musician or a helper, asked here: a confirm() in the page would stop it
// answering other apps until someone answers.
ipcMain.handle('dialog:confirm', async (_e, message, yes) => {
  if (!win) return false;
  const { response } = await dialog.showMessageBox(win, {
    type: 'question', message: String(message), buttons: [String(yes || 'OK'), 'Cancel'], defaultId: 1, cancelId: 1,
  });
  return response === 0;
});

// ---------- permissions ----------
ipcMain.handle('media:status', () => {
  if (!isMac) return { camera: 'granted', microphone: 'granted' };
  return { camera: systemPreferences.getMediaAccessStatus('camera'), microphone: systemPreferences.getMediaAccessStatus('microphone') };
});
ipcMain.handle('media:ask', async (_e, kind) => {
  if (!isMac || testMode) return true;
  return systemPreferences.askForMediaAccess(kind === 'microphone' ? 'microphone' : 'camera');
});
ipcMain.on('media:open-settings', (_e, kind) => {
  if (isMac) shell.openExternal(`x-apple.systempreferences:com.apple.preference.security?Privacy_${kind === 'microphone' ? 'Microphone' : 'Camera'}`);
});
// Which face tracking this computer runs, and why (tracker.js): in the log, and for other apps
// as the state gaze.faceTracking, e.g. "CPU, software graphics (…)".
ipcMain.on('media:tracking', (_e, text) => {
  suite.tracking = String(text).slice(0, 200);
  log.info(`Face tracking: ${suite.tracking}`);
  suite.link?.state('faceTracking', suite.tracking);
});
ipcMain.on('window:on-top', (_e, on) => { win?.setAlwaysOnTop(!!on, 'floating'); buildMenu(); });
ipcMain.on('open-external', (_e, url) => { if (/^https:\/\//.test(url)) shell.openExternal(url); });

// ---------- window ----------
const stateFile = () => path.join(app.getPath('userData'), 'window.json');
function loadBounds() {
  try {
    const b = JSON.parse(fs.readFileSync(stateFile(), 'utf8'));
    const area = screen.getDisplayMatching(b).workArea;
    const visible = b.x < area.x + area.width - 100 && b.y < area.y + area.height - 100 && b.x + b.width > area.x + 100 && b.y > area.y - 20;
    return visible ? b : null;
  } catch { return null; }
}
function saveBounds() {
  try { if (win && !win.isMinimized() && !win.isFullScreen()) fs.writeFileSync(stateFile(), JSON.stringify(win.getBounds())); } catch {}
}

// A message the page repeats (say, every frame) is written once, then counted.
const repeat = { text: '', count: 0 };
function pageMessage(e) {
  if (e.level !== 'warning' && e.level !== 'error') return;
  const text = `Page: ${e.message} (${String(e.sourceId).replace(/^app:\/\/[a-z]+\//, '')}:${e.lineNumber})`;
  if (text === repeat.text) { repeat.count++; return; }
  if (repeat.count) log.info(`(the last message ${repeat.count} more time${repeat.count > 1 ? 's' : ''})`);
  Object.assign(repeat, { text, count: 0 });
  log.write(e.level === 'error' ? 'ERROR' : 'WARNING', text);
}

function createWindow() {
  const area = screen.getPrimaryDisplay().workAreaSize;
  const saved = loadBounds();
  win = new BrowserWindow({
    width: Math.min(1360, area.width), height: Math.min(900, area.height), minWidth: 760, minHeight: 560,
    ...(saved || {}),
    title: 'GazeStage', show: false, autoHideMenuBar: true, backgroundColor: '#101216',
    titleBarStyle: isMac ? 'hiddenInset' : 'default', trafficLightPosition: { x: 16, y: 18 },
    // Keep tracking, timers and the Pro Tools link running when Pro Tools covers the window.
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, backgroundThrottling: false },
  });
  win.once('ready-to-show', () => win.show());
  win.on('close', saveBounds);
  win.on('closed', () => { win = null; synthWin?.destroy(); });   // then the app quits (window-all-closed)
  win.webContents.on('did-start-loading', () => { suite.ready = false; });   // until the page listens again
  // The page's warnings and errors, and a crash or hang, go in the log too.
  win.webContents.on('console-message', pageMessage);
  win.webContents.on('render-process-gone', (_e, d) => log.critical(`The page stopped: ${d.reason}, exit code ${d.exitCode}`));
  win.on('unresponsive', () => log.warn('The window stopped answering'));
  win.on('responsive', () => log.info('The window is answering again'));
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https:\/\//.test(url)) shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith('app://')) e.preventDefault(); });
  win.loadURL('app://gazestage/index.html');
}

// ---------- menu ----------
const send = (cmd) => () => win?.webContents.send('command', cmd);
function buildMenu() {
  const onTop = !!win?.isAlwaysOnTop();
  const template = [
    ...(isMac ? [{
      label: 'GazeStage',
      submenu: [
        { role: 'about' }, { type: 'separator' },
        { label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: send('settings') },
        { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' },
        { type: 'separator' }, { role: 'quit' },
      ],
    }] : [{ label: 'File', submenu: [{ label: 'Settings…', accelerator: 'Ctrl+,', click: send('settings') }, { role: 'quit' }] }]),
    {
      label: 'Control',
      submenu: [
        { label: 'Recenter Pointer', accelerator: 'CmdOrCtrl+R', click: send('recenter') },
        { label: 'Calibrate…', accelerator: 'CmdOrCtrl+K', click: send('calibrate') },
        { label: 'Pause or Resume', accelerator: 'CmdOrCtrl+P', click: send('pause') },
        { type: 'separator' },
        { label: 'Transport', accelerator: 'CmdOrCtrl+1', click: send('page:transport') },
        { label: 'Instrument', accelerator: 'CmdOrCtrl+2', click: send('page:play') },
        { label: 'Tone Pad', accelerator: 'CmdOrCtrl+3', click: send('page:tone') },
        { type: 'separator' },
        { label: 'All Notes Off', accelerator: 'CmdOrCtrl+.', click: send('panic') },
        { label: 'Run Setup Again…', click: send('onboarding') },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Keep Window on Top', type: 'checkbox', checked: onTop, click: send('toggle-on-top') },
        { label: 'Show Camera Preview', accelerator: 'CmdOrCtrl+Shift+C', click: send('toggle-preview') },
        { type: 'separator' }, { role: 'togglefullscreen' },
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        ...(app.isPackaged ? [] : [{ type: 'separator' }, { role: 'toggleDevTools' }]),
      ],
    },
    { role: 'windowMenu' },
    {
      role: 'help',
      submenu: [{ label: 'GazeStage Setup Guide', click: () => shell.openExternal('https://github.com/chittychitty38/Limitless-sound/tree/main/apps/gazestage#readme') }],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  protocol.handle('app', (req) => {
    const rel = decodeURIComponent(new URL(req.url).pathname);
    const file = path.normalize(path.join(ROOT, rel));
    if (!file.startsWith(ROOT)) return new Response('Not found', { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });
  session.defaultSession.setPermissionRequestHandler((_wc, perm, cb) => cb(ALLOWED.has(perm)));
  session.defaultSession.setPermissionCheckHandler((_wc, perm) => ALLOWED.has(perm));
  app.setAboutPanelOptions({
    applicationName: 'GazeStage', applicationVersion: app.getVersion(),
    copyright: 'Limitless Sound', credits: 'Eye, head and sound control for music.',
  });
  openVirtualPorts();
  createWindow();   // joins Limitless Sound once the page is ready (suite:ready)
  buildMenu();
  app.on('activate', () => { if (!win) createWindow(); });
});

// A GPU or helper process that crashed takes face tracking or audio with it: say which.
app.on('child-process-gone', (_e, d) => {
  if (d.reason !== 'clean-exit') log.error(`The ${d.name || d.type} process stopped: ${d.reason}, exit code ${d.exitCode}`);
});
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { quitting = true; });
app.on('will-quit', () => {
  closeVirtualPorts(); suite.link?.stop();
  if (repeat.count) log.info(`(the last message ${repeat.count} more time${repeat.count > 1 ? 's' : ''})`);
});
