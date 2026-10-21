// GazeStage desktop shell.
// - Serves the renderer from app:// so the camera, microphone and Web MIDI work the same on
//   every platform, fully offline.
// - On macOS (and Linux) creates its own virtual MIDI ports, so Pro Tools and any instrument
//   see "GazeStage" with no IAC or loopback setup. Windows falls back to Web MIDI in the page.
// - Builds the native menu, remembers the window, and asks for camera/mic access when the
//   guided setup reaches that step.
const {
  app, BrowserWindow, Menu, protocol, net, session, systemPreferences, ipcMain, shell, screen,
} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);
app.setName('GazeStage');

const ROOT = path.join(__dirname, 'renderer');
const ALLOWED = new Set(['media', 'midi', 'midiSysex']);
const isMac = process.platform === 'darwin';
const testMode = app.commandLine.hasSwitch('use-fake-device-for-media-stream');
let win = null;

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
    closeVirtualPorts();
  }
}
function closeVirtualPorts() {
  for (const p of [midi.out.notes, midi.out.hui, midi.huiIn]) { try { p?.closePort(); } catch {} }
  midi.out = {}; midi.huiIn = null;
}

ipcMain.handle('midi:status', () => ({ native: midi.native, ports: PORTS, error: midi.error }));
ipcMain.on('midi:send', (_e, port, bytes) => {
  const o = midi.out[port];
  if (!o || !Array.isArray(bytes)) return;
  // Split a run of complete messages (e.g. a HUI zone + port pair) into single sends.
  for (let i = 0; i < bytes.length;) {
    const len = (bytes[i] & 0xf0) === 0xc0 || (bytes[i] & 0xf0) === 0xd0 ? 2 : 3;
    o.sendMessage(bytes.slice(i, i + len)); i += len;
  }
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

function createWindow() {
  const area = screen.getPrimaryDisplay().workAreaSize;
  const saved = loadBounds();
  win = new BrowserWindow({
    width: Math.min(1360, area.width), height: Math.min(900, area.height), minWidth: 760, minHeight: 560,
    ...(saved || {}),
    title: 'GazeStage', show: false, autoHideMenuBar: true, backgroundColor: '#101216',
    titleBarStyle: isMac ? 'hiddenInset' : 'default', trafficLightPosition: { x: 16, y: 18 },
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
  });
  win.once('ready-to-show', () => win.show());
  win.on('close', saveBounds);
  win.on('closed', () => { win = null; });
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
  createWindow();
  buildMenu();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => app.quit());
app.on('will-quit', closeVirtualPorts);
