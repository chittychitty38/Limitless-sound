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
    tracking: (text) => ipcRenderer.send('media:tracking', text),
  },
  suite: {
    status: () => ipcRenderer.invoke('suite:status'),
    did: (action) => ipcRenderer.send('suite:did', action),
    invoke: (action, args) => ipcRenderer.invoke('suite:invoke', action, args),
    // Listening for actions is the page's sign that it's ready for them (main.js).
    onInvoke: (cb) => { ipcRenderer.on('suite:invoke', (_e, req) => cb(req)); ipcRenderer.send('suite:ready'); },
    reply: (id, result) => ipcRenderer.send('suite:result', id, result),
    onConnected: (cb) => ipcRenderer.on('suite:connected', (_e, on) => cb(on)),
    onPrefs: (cb) => ipcRenderer.on('suite:prefs', (_e, prefs) => cb(prefs)),
    applied: (values) => ipcRenderer.send('suite:applied', values),
  },
  midi: {
    status: () => ipcRenderer.invoke('midi:status'),
    send: (port, bytes) => ipcRenderer.send('midi:send', port, Array.from(bytes)),
    onHuiIn: (cb) => ipcRenderer.on('midi:hui-in', (_e, bytes) => cb(bytes)),
  },
});
