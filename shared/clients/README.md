# Limitless Link clients

Connect an app to the Limitless Sound hub. Each is one file to copy into the app, and each
does nothing when the hub isn't running.

| Language | File | Used by |
|---|---|---|
| Python 3.10+ | [`python/limitless_link.py`](python/limitless_link.py) (standard library only) | Voice, One-Hand, Zoom, Control |
| Node / Electron main | [`js/limitless-link.js`](js/limitless-link.js) (no dependencies) | GazeStage |
| Rust | [`rust/`](rust) (`serde_json`) | Limitless Color |

All three are tested end to end against the real hub in `shared/hub/tests/`.

Python apps also carry [`python/applog.py`](python/applog.py): a log file per app
(`~/Library/Logs/Limitless Sound/` on Mac, `%LOCALAPPDATA%\Limitless Sound\Logs\` on Windows)
that records every uncaught error and where the app was if it crashes. Call
`applog.start("<App name>", __version__)` first thing. Copies of both files must stay identical
to these; `shared/hub/tests` checks that.
