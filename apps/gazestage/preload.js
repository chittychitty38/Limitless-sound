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
  suite: {
    status: () => ipcRenderer.invoke('suite:status'),
    did: (action) => ipcRenderer.send('suite:did', action),
    invoke: (action, args) => ipcRenderer.invoke('suite:invoke', action, args),
    onInvoke: (cb) => ipcRenderer.on('suite:invoke', (_e, req) => cb(req)),
    reply: (id, result) => ipcRenderer.send('suite:result', id, result),
    onConnected: (cb) => ipcRenderer.on('suite:connected', (_e, on) => cb(on)),
  },
  midi: {
    status: () => ipcRenderer.invoke('midi:status'),
    outputs: () => ipcRenderer.invoke('midi:outputs'),
    openTone: (name) => ipcRenderer.invoke('midi:open-tone', name),
    send: (port, bytes) => ipcRenderer.send('midi:send', port, Array.from(bytes)),
    onHuiIn: (cb) => ipcRenderer.on('midi:hui-in', (_e, bytes) => cb(bytes)),
  },
});
