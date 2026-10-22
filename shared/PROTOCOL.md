# Limitless Link protocol (version 1)

How a Limitless Sound app talks to the Limitless Sound hub. Use a client in
`shared/clients/` (Python, JavaScript, Rust or C++) rather than writing this by hand.

## Finding the hub

The hub writes `link.json` to the suite's shared folder when it starts:

| | Folder |
|---|---|
| Mac | `~/Library/Application Support/Limitless Sound/` |
| Windows | `%APPDATA%\Limitless Sound\` |
| Linux | `~/.config/Limitless Sound/` |
| Tests | `$LIMITLESS_SOUND_HOME` overrides the folder |

```json
{"protocol": 1, "port": 47900, "http": 47901, "token": "…", "pid": 1234, "version": "0.1.0"}
```

The file is readable only by the signed-in user. The token proves a connection comes from
that user and not from a web page. If the file is missing or the port refuses, the hub
isn't running: try again every couple of seconds and otherwise carry on as normal. **An
app must work exactly the same without the hub.**

## Connection

TCP to `127.0.0.1:<port>`, UTF-8 JSON, one object per line (`\n`), at most 64 KB a line.
The first message must be `hello`, within 5 seconds.

### App → hub

| op | Fields | Meaning |
|---|---|---|
| `hello` | `token`, `tool`, `name`, `version`, `actions`, `subscribe` | Join. `tool` is a short lowercase id (`voice`, `onehand`, `zoom`, `color`, `control`, `gaze`, or a new one). `subscribe` is a list of event patterns, default `["*"]`. A second `hello` for the same tool replaces the first connection. |
| `actions` | `actions` | Replace this app's action list. |
| `invoke` | `action`, `args`, `id`, `depth` | Ask the suite to do something: `zoom.in`, `daw.record`, `hub.say`. The answer comes back as `result` with the same `id`. |
| `did` | `action`, `intent`?, `value`?, `depth` | "I just did this", whatever input caused it. Becomes the events `<tool>.<action>` and, if the action has an intent, `<intent>`. |
| `state` | `key`, `value`, `depth` | A state changed. Becomes the event `<tool>.<key>` (or `app.<x>` for shared keys like `app.daw`). Only sent on as an event when the value actually changes. |
| `say` | `text` | Speak through the suite's one voice. |
| `result` | `id`, `ok`, `message` | Answer to an `invoke` from the hub, within 3 seconds. |
| `ping` | | Hub answers `pong`. |

### Hub → app

| op | Fields | Meaning |
|---|---|---|
| `welcome` | `prefs`, `actions`, `states`, `tools` | Accepted. |
| `invoke` | `id`, `action`, `args`, `source`, `depth` | Do one of your actions (id without the tool prefix). Reply with `result`. While handling it, send `did`/`state` with the same `depth`. |
| `event` | `name`, `value`, `source` | Something happened somewhere in the suite. Apps never receive their own events. |
| `prefs` | `prefs` | Shared accessibility settings changed. |
| `actions` | `actions`, `tools` | The suite's action list changed (an app opened or closed). |
| `result` | `id`, `ok`, `message` | Answer to your `invoke`. |
| `error` | `message` | Something was wrong. Before `welcome`, the hub closes the connection. |

## Actions

An action is `{"id", "label", "intent"?, "phrases"?, "args"?}`:

- `label`: what a person sees and hears ("Zoom in"). Plain language.
- `intent`: one of the shared DAW intents below, when this action does that job.
- `phrases`: extra ways to say it, for Limitless Voice.
- `args`: argument names and types, e.g. `{"phrase": "text"}`.

Across the suite an action is called `<tool>.<id>`. The hub's own actions are
`hub.say {text}`, `hub.open {tool}`, `hub.openAll`, `hub.settings`, `hub.status`.

### Shared DAW intents

`daw.playStop`, `daw.play`, `daw.stop`, `daw.record`, `daw.start`, `daw.undo`, `daw.redo`,
`daw.save`, `daw.mute`, `daw.solo`, `daw.nextTrack`, `daw.prevTrack`, `daw.zoomIn`,
`daw.zoomOut`, `daw.zoomFit`, `daw.metronome`, `daw.mixer`.

Invoking an intent goes to the first open app that declares it, in the musician's chosen
order (default: zoom, control, onehand, gaze, voice). When none is open, an installed app
with a command line can still answer (Limitless Zoom via `--do`).

## Events

| Event | Value | From |
|---|---|---|
| `<tool>.<action>` | the `did` value | any app, after doing something |
| `daw.*` | `{"by": tool, "action": id}` | any app, after doing an action with that intent |
| `<tool>.connected` | `true` / `false` | hub |
| `voice.listening` | `"awake"`, `"asleep"`, `"take"` | Limitless Voice |
| `onehand.mode` | `true` / `false` | Limitless One-Hand |
| `zoom.keys` | `true` / `false` | Limitless Zoom |
| `color.filter` | `true` / `false` | Limitless Color |
| `control.enabled`, `control.layer` | bool, number | Limitless Control |
| `gaze.tracking` | bool | GazeStage |
| `app.front`, `app.daw` | app name, bool | any app that watches the front app |
| `hub.speaking` | bool | hub, while the one voice is talking |

## Sidechain links

The hub keeps a list of links, editable on its settings page:

```json
{"id": "take-guard", "name": "While recording, …", "when": {"event": "daw.record"},
 "do": [{"action": "voice.takeGuard"}], "on": true}
```

`when.event` may end in `*`; `when.value`, if given, must equal the event's value.
A chain of links stops after 4 steps, and a link that fires more than 8 times in 2 seconds
is switched off and reported.

## Shared preferences

`speak`, `oneVoice`, `textScale` (1.0–2.0), `highContrast`, `reduceMotion`, `dwellMs`
(250–3000), `scanMs` (400–5000). Apps apply the ones they support. When `oneVoice` is on
and the app is connected, `say` through the hub instead of speaking directly; the Python
client's `say()` returns `False` when the app should speak for itself.

After applying a `prefs` message (and the prefs in `welcome`), report what you honored as
the state `prefs.applied`: an object of each shared setting you support, with the value you
are now using. For example `{"textScale": 1.5, "highContrast": true, "reduceMotion": true}`.
That is how the settings page, and the Limitless Access Standard test kit
(`standard/conformance/`), know a setting reached you. Send it within 3 seconds.

## HTTP (settings page and one-shot triggers)

`http://127.0.0.1:<http>/`. Requests need the token: `X-Limitless-Token` header, or `?t=`
on GET. The Host header must be `127.0.0.1:<http>` or `localhost:<http>`.

| | |
|---|---|
| `GET /?t=…` | Settings page |
| `GET /do/<action>?t=…&arg=value` | Run an action; plain-text answer, 200 or 409 |
| `GET /api/state?since=<seq>` | Tools, actions, links, prefs, states, activity log |
| `POST /api/invoke` | `{"action", "args"}` |
| `POST /api/prefs`, `/api/routes`, `/api/intent-order`, `/api/start-tools`, `/api/autostart`, `/api/open`, `/api/install-path` | Settings |
