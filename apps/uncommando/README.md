# Uncommando

Part of **Limitless Sound**: music software that leaves no one behind.

Every DAW gives you one undo. Undoing a plugin tweak means also undoing the edit you
made after it, or digging through the history list. Uncommando gives you two:

| Shortcut | Does |
|---|---|
| **⌘Z** | Your DAW's own undo, for everything except plugin changes: edits, regions, notes, mixing. |
| **⌥⌘Z** | Undo only plugin changes, newest first, across **every** plugin in the session. Hold it to keep going. |
| **⌥⇧⌘Z** | Redo plugin changes. |
| **hold ⌃⌥⌘Z** | Hear the sound **before** your last plugin change; let go to hear it after. An instant A/B for every tweak. |
| **⌃⌥⌘H** | The plugin change history: every knob move, in which plugin, from what to what. |
| **⌃⌥⌘/** | Show my shortcuts for the app in front, in big text. |

It also lets you **make your own shortcuts for any DAW or app**. A shortcut can press other
keys or a sequence of them, choose a menu item by name (it keeps working however the DAW's
own key commands are set), press a button by name, type text, say something, run any
Limitless Sound action (zoom, voice, color...), or do several of these one after another.
Each DAW gets its own shortcuts, with ones shared by every DAW and ones for every app.
Every one of them, including the undo shortcuts, can be changed or switched off.

Mac first: macOS 12 or newer, Apple Silicon and Intel.

## How it works in each DAW

**Logic Pro: works with every plugin, nothing to install.**
Every Logic plugin window has its own Undo and Redo buttons, but no command undoes "the
last change in whichever plugin I touched". Uncommando watches which plugin windows you
click, drag or scroll in, keeps them in one time order, and presses the right window's
Undo button. For ⌘Z to leave plugin changes alone, turn them out of Logic's main undo once:
**Edit › Undo History**, then next to **Include Parameter Changes From** turn **Plug-in** off
(older Logic versions: a plugin window's settings menu › **Include Plug-In Undo Steps in
Project Undo History**). Setup has a button that opens it for you. Keep a plugin's window
open while you tweak it: once the window closes, its changes can't be reached.

**Pro Tools, Ableton Live, Cubase and the rest: the Uncommando plugin.**
Pro Tools keeps no undo for plugin changes at all, so Uncommando also comes as a plugin
that holds another plugin. Insert **Uncommando** (or **Uncommando Instrument**, for
instruments) on a track, choose your plugin inside it, and every change you make to that
plugin is remembered: in time order with every other Uncommando plugin in the session,
with names and values ("Band 2 Gain back to −3.1 dB"), even with the window closed, and
**even after you close and reopen the session**. It also works in Logic, for plugins you
want to undo with their window closed.

- The DAW still sees and automates the plugin's parameters, under their own names.
- Automation playing back is never recorded as a change.
- **DAW sees knob moves** (on by default): on, your DAW records the moves as automation and
  may also put them in its own undo. Off, they stay out of the DAW completely, so ⌘Z can
  never undo them, but they aren't recorded as automation either.
- The window has its own Undo, Redo and "Hold: before" buttons, and ⌥⌘Z works in it too.

**Plain ⌘Z** is never touched: it goes to your DAW as always.

**Shortcuts that DAWs already use.** ⌥⌘Z is Restore Last Selection in Pro Tools and Undo
History in some Logic versions. While Uncommando runs, ⌥⌘Z does plugin undo instead
(those commands are still in the Edit menu). To keep the DAW's meaning, change the plugin
undo shortcut in My shortcuts, or add a "Let the app have this shortcut" for that DAW. The
shortcut editor warns you whenever a shortcut replaces something.

## Installing

Download `Uncommando-mac-apple-silicon.dmg` (M1 and newer) or
`Uncommando-mac-intel.dmg` from the Releases page or a build's artifacts.

1. Drag Uncommando onto Applications and open it. It isn't signed by Apple yet: the
   first time, go to System Settings › Privacy & Security and click **Open Anyway**.
2. Setup opens. Click **Allow…** next to Accessibility and Input Monitoring; each turns into
   a green tick as soon as it's allowed.
3. In Logic, use Setup's **Open Logic's Undo History** button (above).
4. For Pro Tools and other DAWs, click **Install the Uncommando plugin**, then restart the
   DAW. The AU and VST3 go into your own Plug-Ins folders.
5. Move a plugin knob and press ⌥⌘Z. Setup shows each shortcut it hears.

The menu bar icon has: undo and redo plugin change, Plugin changes…, My shortcuts…,
Show my shortcuts for this app, Pause, speech on or off, Open at login, Setup, and
**Save a report of the window in front**, which writes what Uncommando can see in a
window to your Desktop, for making it work with an app it doesn't know yet.

## Your shortcuts file

`~/Library/Application Support/Uncommando/shortcuts.json`. Edit it in **My shortcuts**,
or by hand, and share it with **Export** and **Import**:

```json
{"version": 1, "apps": {
  "daws":  {"bindings": [{"keys": "alt+cmd+z", "do": {"plugin": "undo"}, "repeat": true}]},
  "logic": {"bindings": [
    {"keys": "f13", "do": {"menu": "File > Bounce > Project or Section…"}},
    {"keys": "ctrl+alt+cmd+b", "do": {"steps": [{"keys": "cmd+a"}, {"wait": 0.1}, {"menu": "Edit > Copy"}]}}]},
  "protools": {"bindings": [{"keys": "alt+cmd+z", "do": {"pass": true}}]}
}}
```

Profiles: `daws` (every DAW), `*` (every app), a DAW (`logic`, `protools`, `ableton`,
`cubase`, `studioone`, `reaper`, `bitwig`, `flstudio`, `garageband`, `dp`, `reason`), or any
app's bundle id. The most specific one wins. What a shortcut can do is listed at the top of
[`uncommando/profiles.py`](uncommando/profiles.py). Shortcuts are physical key
positions, so they stay on the same keys with any keyboard layout. A file with a mistake in
it is kept as `shortcuts.broken.json` and the defaults are used, so a typo never leaves you
without your keys.

## Works with the rest of Limitless Sound

With the Limitless Sound hub running, any other app can undo a plugin change: say
"undo plugin" to Limitless Voice, press a button on an adaptive controller, glance at it in
GazeStage. Your shortcuts can run any action in the suite, and spoken feedback goes through
the suite's one voice. Actions: `uncommando.pluginUndo`, `pluginRedo`, `pluginBefore`,
`pluginAfter`, `undoFront`, `pluginHistory`, `cheatSheet`, `press {shortcut}`, `pause`,
`resume`. Without the hub, `"Uncommando" --do pluginUndo` does the same from Stream
Deck, Shortcuts or a script.

## For developers

```
pip install -r requirements.txt pytest pyinstaller
QT_QPA_PLATFORM=offscreen python -m pytest      # 58 tests, plus 1 that needs the plugin's test program
python -m uncommando                        # run from source
pyinstaller packaging/uncommando.spec       # build the app (bundles plugins/ if it's there)
```

The plugin (C++, [JUCE](https://juce.com) 8), in [`plugin/`](plugin):

```
cmake -S plugin -B plugin/build -DCMAKE_BUILD_TYPE=Release   # downloads JUCE 8.0.12
cmake --build plugin/build -j
ctest --test-dir plugin/build                                # undo history and plugin tests
UNCOMMANDO_TEST_BINARY=plugin/build/undo_plugin_tests_artefacts/Release/undo_plugin_tests \
  python -m pytest tests/test_plugin_link.py                 # the app and the real plugin, end to end
```

`-DUNCOMMANDO_AAX=ON` adds the Pro Tools (AAX) build, using the AAX SDK that comes with
JUCE. Pro Tools only loads AAX plugins signed with PACE's tools, which needs a free Avid
developer account and a PACE agreement, so the AAX build isn't in the releases yet.

GitHub Actions (`.github/workflows/uncommando.yml`) runs every test, builds the plugin as a
universal (Apple Silicon and Intel) AU and VST3, checks the AUs with Apple's `auval`, builds
the app with the plugin inside, runs its self test, and makes the disk images.

Layout:

| | |
|---|---|
| `keys.py`, `daws.py` | Shortcut names, and the DAWs it knows with some of their own key commands |
| `profiles.py` | Your shortcuts: loading, checking, the most specific profile winning |
| `engine.py` | Decides, for every key pressed anywhere, whether it's one of your shortcuts |
| `runner.py` | Does what a shortcut says, off the keyboard thread |
| `timeline.py` | One undo history for every plugin in the session, in time order |
| `plugin_undo.py` | Plugin undo, redo and compare over Logic's windows and Uncommando plugins |
| `undo_link.py` | The local connection Uncommando plugins report to |
| `logic_windows.py`, `macax.py` | Logic's plugin windows, through the Accessibility API |
| `platforms.py` | Catching shortcuts, pressing keys, permissions (Mac; Linux for tests) |
| `ui.py`, `app.py`, `suite.py` | Windows, menu bar and wiring, the suite link |
| `plugin/core/UndoHistory.*` | The plugin's undo history: gestures, grouping, automation, saving |
| `plugin/source/` | The JUCE plugin: hosting, the editor, the plugin browser, the link |

## Status and known gaps

Tested here: everything above runs on Linux, where the Python app's 59 tests pass (logic,
link, windows, and the app and a real Uncommando plugin undoing a change end to end) and
the plugin builds as VST3 with no warnings and passes its own tests. **Not yet tried on a
real Mac, in a real DAW.** The first Mac build needs hands-on testing, in particular:

- Logic's plugin-window Undo and Redo buttons are found by their accessibility names
  ("Undo", "Redo"), and a plugin window is told apart from other windows by also having
  "Compare", "Bypass", "Link", "Copy" or "Paste". Logic's exact names are unconfirmed. If they
  differ, set `logic_plugin_markers` in `settings.json` and send a **Save a report of the
  window in front** to fix the defaults. Logic in another language needs its own names.
- In Logic, a click in a plugin window that doesn't change anything still counts as a
  change, so the next ⌥⌘Z may undo an older change in that plugin.
- Hosting a plugin inside the Uncommando AU in Logic has only been built, not run.
- Pro Tools needs the PACE-signed AAX, above.
- Windows isn't supported yet; the engine and the plugin are written to allow it.
- Not code-signed. Signing needs an Apple Developer ID.

The plugin is built with JUCE, which is free under the AGPLv3: releasing builds of it means
releasing this folder under the AGPLv3 too, or buying a JUCE licence. Choose before the
first public release.
