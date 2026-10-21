// GazeStage desktop shell. Serves the renderer from app:// so the camera, microphone and
// Web MIDI work the same on macOS, Windows and Linux, fully offline.
const { app, BrowserWindow, protocol, net, session, systemPreferences, ipcMain } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);

const ROOT = path.join(__dirname, 'renderer');
const ALLOWED = new Set(['media', 'midi', 'midiSysex']);

function createWindow() {
  const win = new BrowserWindow({
    width: 1280, height: 860, minWidth: 720, minHeight: 520,
    title: 'GazeStage', autoHideMenuBar: true, backgroundColor: '#0f1115',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
  });
  win.loadURL('app://gazestage/index.html');
  ipcMain.on('always-on-top', (_e, on) => win.setAlwaysOnTop(!!on, 'floating'));
}

app.whenReady().then(async () => {
  protocol.handle('app', (req) => {
    const rel = decodeURIComponent(new URL(req.url).pathname);
    const file = path.normalize(path.join(ROOT, rel));
    if (!file.startsWith(ROOT)) return new Response('Not found', { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });
  session.defaultSession.setPermissionRequestHandler((_wc, perm, cb) => cb(ALLOWED.has(perm)));
  session.defaultSession.setPermissionCheckHandler((_wc, perm) => ALLOWED.has(perm));
  if (process.platform === 'darwin') {
    await systemPreferences.askForMediaAccess('camera').catch(() => {});
  }
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => app.quit());
