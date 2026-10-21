const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('gazestage', {
  setAlwaysOnTop: (on) => ipcRenderer.send('always-on-top', on),
});
