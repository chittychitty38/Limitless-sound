// Limitless Link for Node and Electron (main process): connect an app to the Limitless Sound hub.
// One file, no dependencies. Reconnects by itself and does nothing when the hub isn't running.
//
//   const { Link } = require('./limitless-link');
//   const link = new Link({ tool: 'gaze', name: 'GazeStage', version: '0.2.0',
//     actions: [{ id: 'play', label: 'Play', intent: 'daw.play' }],
//     onInvoke: (action, args, source) => [true, 'Playing'] });
//   link.start();
//   link.did('play');  link.state('tracking', true);
//   link.invoke('daw.record').then((r) => ...);   // r = { ok, message }
//
// Protocol: shared/PROTOCOL.md.
'use strict';
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');

function configDir() {
  if (process.env.LIMITLESS_SOUND_HOME) return process.env.LIMITLESS_SOUND_HOME;
  if (process.platform === 'darwin') return path.join(os.homedir(), 'Library', 'Application Support', 'Limitless Sound');
  if (process.platform === 'win32') return path.join(process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming'), 'Limitless Sound');
  return path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'Limitless Sound');
}

// The installed Limitless Sound hub, if there is one.
function hubApp() {
  const candidates = process.platform === 'darwin'
    ? ['/Applications/Limitless Sound.app', path.join(os.homedir(), 'Applications', 'Limitless Sound.app')]
    : process.platform === 'win32' && process.env.LOCALAPPDATA
      ? [path.join(process.env.LOCALAPPDATA, 'Programs', 'Limitless Sound', 'Limitless Sound.exe')] : [];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

// Start the installed hub in the background. true if it was found.
function launchHub() {
  const app = hubApp();
  if (!app) return false;
  const { spawn } = require('node:child_process');
  try {
    const child = process.platform === 'darwin'
      ? spawn('open', ['-g', '-j', app, '--args', '--background'], { detached: true, stdio: 'ignore' })
      : spawn(app, ['--background'], { detached: true, stdio: 'ignore', windowsHide: true });
    child.on('error', () => {});
    child.unref();
    return true;
  } catch { return false; }
}

class Link extends EventEmitter {
  // Events: 'connected' (bool), 'event' (name, value, source), 'prefs' (prefs), 'actions' (list)
  constructor({ tool, name, version = '', actions = [], onInvoke = null, subscribe = ['*'], retryMs = 2000, startHub = true }) {
    super();
    Object.assign(this, { tool, name, version, onInvoke, subscribe, retryMs, startHub });
    this._triedHub = false;
    this.actions = actions;
    this.connected = false;
    this.prefs = {};
    this.suiteActions = [];
    this.states = {};
    this._sock = null; this._timer = null; this._stopped = false; this._ids = 1; this._waiting = new Map(); this._depth = 0;
  }

  start() { this._stopped = false; this._connect(); return this; }
  stop() { this._stopped = true; clearTimeout(this._timer); this._sock?.destroy(); }

  setActions(actions) { this.actions = actions; this._send({ op: 'actions', actions }); }
  did(action, intent, value) {
    const m = { op: 'did', action, depth: this._depth };
    if (intent) m.intent = intent;
    if (value !== undefined) m.value = value;
    this._send(m);
  }
  state(key, value) { this._send({ op: 'state', key, value, depth: this._depth }); }
  // true when the hub speaks for the suite; false means speak yourself.
  say(text) { return this.connected && this.prefs.oneVoice !== false && this._send({ op: 'say', text }); }
  invoke(action, args = {}, timeoutMs = 4000) {
    return new Promise((resolve) => {
      const id = this._ids++;
      if (!this._send({ op: 'invoke', id, action, args, depth: this._depth })) {
        resolve({ ok: false, message: 'Limitless Sound isn’t running.' }); return;
      }
      const t = setTimeout(() => { this._waiting.delete(id); resolve({ ok: false, message: 'No answer.' }); }, timeoutMs);
      this._waiting.set(id, (r) => { clearTimeout(t); resolve({ ok: !!r.ok, message: r.message || '' }); });
    });
  }

  _send(msg) {
    if (!this._sock || (!this.connected && msg.op !== 'hello')) return false;
    try { this._sock.write(JSON.stringify(msg) + '\n'); return true; } catch { return false; }
  }

  _retry() {
    if (this._stopped) return;
    if (this.startHub && !this._triedHub && !this.connected) {
      // Every app brings the suite up with it: open the hub if it's installed.
      this._triedHub = true;
      launchHub();
    }
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._connect(), this.retryMs);
    this._timer.unref?.();
  }

  _connect() {
    let info;
    try { info = JSON.parse(fs.readFileSync(path.join(configDir(), 'link.json'), 'utf8')); } catch { return this._retry(); }
    if (!info?.port || !info?.token) return this._retry();
    const sock = net.createConnection({ host: '127.0.0.1', port: info.port });
    sock.setNoDelay(true);
    sock.unref?.(); // never keep an app alive just for the link
    this._sock = sock;
    let buf = '';
    sock.on('connect', () => this._send({ op: 'hello', protocol: 1, token: info.token, tool: this.tool, name: this.name,
      version: this.version, actions: this.actions, subscribe: this.subscribe }));
    sock.on('data', (d) => {
      buf += d.toString('utf8');
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        if (msg && typeof msg === 'object') this._handle(msg);
      }
    });
    sock.on('error', () => {});
    sock.on('close', () => {
      if (this._sock === sock) this._sock = null;
      if (this.connected) { this.connected = false; this.emit('connected', false); }
      this._retry();
    });
  }

  async _handle(msg) {
    switch (msg.op) {
      case 'welcome':
        this.connected = true; this.prefs = msg.prefs || {}; this.suiteActions = msg.actions || []; this.states = msg.states || {};
        this.emit('connected', true); this.emit('prefs', this.prefs); this.emit('actions', this.suiteActions);
        break;
      case 'invoke': {
        let ok = true, message = '';
        this._depth = msg.depth || 0;
        try {
          const r = this.onInvoke ? await this.onInvoke(msg.action, msg.args || {}, msg.source || '') : [false, 'This app takes no actions.'];
          if (Array.isArray(r)) { ok = !!r[0]; message = String(r[1] ?? ''); }
          else if (typeof r === 'boolean') ok = r;
          else if (typeof r === 'string') message = r;
        } catch (e) { ok = false; message = String(e?.message || e); }
        this._depth = 0;
        this._send({ op: 'result', id: msg.id, ok, message });
        break;
      }
      case 'event': this.states[msg.name] = msg.value; this.emit('event', msg.name, msg.value, msg.source); break;
      case 'prefs': this.prefs = msg.prefs || {}; this.emit('prefs', this.prefs); break;
      case 'actions': this.suiteActions = msg.actions || []; this.emit('actions', this.suiteActions); break;
      case 'result': { const cb = this._waiting.get(msg.id); if (cb) { this._waiting.delete(msg.id); cb(msg); } break; }
      case 'error': if (!this.connected) this._sock?.destroy(); break;
    }
  }
}

module.exports = { Link, configDir, launchHub };
