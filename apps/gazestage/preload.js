const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('gazestage', {
  platform: process.platform,
  setAlwaysOnTop: (on) => ipcRenderer.send('window:on-top', on),
  openExternal: (url) => ipcRenderer.send('open-external', url),
  onCommand: (cb) => ipcRenderer.on('command', (_e, cmd) => cb(cmd)),
  media: {
    status: () => ipcRenderer.invoke('media:status'),
    ask: (kind) => ipcRenderer.invoke('media:ask', kind),
    openSettings: (kind) => ipcRenderer.send('media:open-settings', kind),
  },
  midi: {
    status: () => ipcRenderer.invoke('midi:status'),
    send: (port, bytes) => ipcRenderer.send('midi:send', port, Array.from(bytes)),
    onHuiIn: (cb) => ipcRenderer.on('midi:hui-in', (_e, bytes) => cb(bytes)),
  },
});
