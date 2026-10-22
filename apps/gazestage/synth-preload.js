// The built-in instrument's hidden page (renderer/synth.html) gets its end of the channel to
// GazeStage's window here (main.js), and nothing else.
const { ipcRenderer } = require('electron');

ipcRenderer.on('synth:port', (e) => window.postMessage('gazestage:synth-port', '*', e.ports));
