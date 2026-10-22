# Limitless Link clients

Connect an app to the Limitless Sound hub. Each is one file to copy into the app, and each
does nothing when the hub isn't running.

| Language | File | Used by |
|---|---|---|
| Python 3.10+ | [`python/limitless_link.py`](python/limitless_link.py) (standard library only) | Voice, One-Hand, Zoom, Control |
| Node / Electron main | [`js/limitless-link.js`](js/limitless-link.js) (no dependencies) | GazeStage |
| Rust | [`rust/`](rust) (`serde_json`) | Limitless Color |
| C++17 | [`cpp/limitless_link.hpp`](cpp) (one header, standard library and OS sockets only) | Instrument, plug-in (JUCE) and hardware makers |

All four are tested end to end against the real hub in `shared/hub/tests/`.
