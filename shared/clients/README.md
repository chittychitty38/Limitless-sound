# Limitless Link clients

Connect an app to the Limitless Sound hub. Each is one file to copy into the app, and each
does nothing when the hub isn't running.

| Language | File | Used by |
|---|---|---|
| Python 3.10+ | [`python/limitless_link.py`](python/limitless_link.py) (standard library only) | Voice, One-Hand, Zoom, Control |
| Node / Electron main | [`js/limitless-link.js`](js/limitless-link.js) (no dependencies) | GazeStage |
| Rust | [`rust/`](rust) (`serde_json`) | Limitless Color |

All three are tested end to end against the real hub in `shared/hub/tests/`.

Every app also carries an applog: a log file per app, in one folder for the whole suite
(`~/Library/Logs/Limitless Sound/` on Mac, `%LOCALAPPDATA%\Limitless Sound\Logs\` on Windows),
that keeps the newest megabyte and records every error nothing caught. Start it first thing:

| Language | File | Start |
|---|---|---|
| Python | [`python/applog.py`](python/applog.py) | `applog.start("<App name>", __version__)` (also notes where a native crash happened) |
| Node / Electron main | [`js/applog.js`](js/applog.js) | `const log = require('./applog').start('<App name>', version)` |
| Rust | [`rust/src/applog.rs`](rust/src/applog.rs) | `applog::start("<App name>", env!("CARGO_PKG_VERSION"))` (times in UTC) |

The settings page's **Activity › Open the log folder** shows the folder. Copies of the client
and applog files must stay identical to these; `shared/hub/tests` checks that.
