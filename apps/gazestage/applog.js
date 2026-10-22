// A log file for a Limitless Sound app made with Node or Electron, so a problem can be found
// after the fact. The same folder and format as the Python apps' applog.py:
//
//   Mac      ~/Library/Logs/Limitless Sound/<App>.log
//   Windows  %LOCALAPPDATA%\Limitless Sound\Logs\<App>.log
//   Linux    ~/.local/state/Limitless Sound/<App>.log
//
// A packaged app has no console, so without this an error leaves no trace. This keeps the
// newest megabyte (plus one older file, <App>.log.1) and records every error nothing caught.
// It never changes what the app does with that error. The log never leaves the computer; a
// musician can send it when asking for help.
//
// Copy this file into the app next to limitless-link.js and start it first thing:
//
//   const log = require('./applog').start('GazeStage', app.getVersion());
//   log.info('Camera ready'); log.warn('No MIDI ports'); log.error('Model failed', err);
//
// Node's standard library only. Writes are synchronous (to a file kept open), so the last line
// before a crash is kept.
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const KEEP_BYTES = 1024 * 1024;

function logDir() {
  if (process.env.LIMITLESS_SOUND_LOGS) return process.env.LIMITLESS_SOUND_LOGS;
  if (process.platform === 'darwin') return path.join(os.homedir(), 'Library', 'Logs', 'Limitless Sound');
  if (process.platform === 'win32') {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
    return path.join(base, 'Limitless Sound', 'Logs');
  }
  return path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local', 'state'), 'Limitless Sound');
}

// Local time as Python's logging writes it: 2026-10-22 11:29:13,123
function stamp(d = new Date()) {
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())},${p(d.getMilliseconds(), 3)}`;
}

function describe(part) {
  if (part instanceof Error) return part.stack || `${part.name}: ${part.message}`;
  if (typeof part === 'string') return part;
  try { return JSON.stringify(part); } catch { return String(part); }
}

class AppLog {
  // The file stays open, so a line costs one write: opening the file for every line held up
  // Electron's main thread (and with it the window) on a busy Mac.
  constructor(app, file) {
    this.app = app;
    this.file = file;
    this.fd = fs.openSync(file, 'a');
    this.size = fs.fstatSync(this.fd).size;
  }

  write(level, ...parts) {
    const line = `${stamp()} ${level.padEnd(7)} ${this.app}: ${parts.map(describe).join(' ')}\n`;
    try {
      const bytes = Buffer.byteLength(line);
      if (this.size + bytes >= KEEP_BYTES && this.size > 0) {
        // Closed first: Windows can't rename a file that's open.
        fs.closeSync(this.fd);
        this.fd = null;
        fs.renameSync(this.file, `${this.file}.1`);
        this.fd = fs.openSync(this.file, 'a');
        this.size = 0;
      }
      if (this.fd === null) this.fd = fs.openSync(this.file, 'a');
      fs.writeSync(this.fd, line);
      this.size += bytes;
    } catch {
      // A log that can't be written must never stop the app.
    }
  }

  info(...parts) { this.write('INFO', ...parts); }
  warn(...parts) { this.write('WARNING', ...parts); }
  error(...parts) { this.write('ERROR', ...parts); }
  critical(...parts) { this.write('CRITICAL', ...parts); }
}

// Does nothing, for when the folder can't be written; the app carries on without a log.
const NO_LOG = { file: null, write() {}, info() {}, warn() {}, error() {}, critical() {} };

function start(app, version = '') {
  let log;
  try {
    const folder = logDir();
    fs.mkdirSync(folder, { recursive: true });
    log = new AppLog(app, path.join(folder, `${app}.log`));
  } catch {
    return NO_LOG;
  }
  // Errors nothing caught still get written down. The monitor only watches, so the app (or
  // Electron) still handles the error exactly as it would have.
  process.on('uncaughtExceptionMonitor', (err, origin) => {
    log.critical(origin === 'unhandledRejection' ? 'Unhandled rejection' : 'Uncaught error', err);
  });
  // Electron's main process only warns about these and carries on, so listening changes nothing.
  if (process.versions.electron) process.on('unhandledRejection', (reason) => log.error('Unhandled rejection', reason));

  const system = { darwin: 'Darwin', win32: 'Windows', linux: 'Linux' }[process.platform] || process.platform;
  const runtime = process.versions.electron ? `Electron ${process.versions.electron}` : `Node ${process.versions.node}`;
  // Electron knows the macOS or Windows version itself; os.release() is the kernel's.
  const release = typeof process.getSystemVersion === 'function' ? process.getSystemVersion() : os.release();
  log.info(`Started ${app} ${version} on ${system} ${release} (${os.arch()}), ${runtime}`);
  return log;
}

module.exports = { start, logDir, KEEP_BYTES };
