//! Limitless Link for Rust: connect an app to the Limitless Sound hub.
//! (A copy of shared/clients/rust/src/lib.rs: update it from there, never by hand.)
//!
//! Standard library plus `serde_json`. Runs on its own thread, reconnects by itself,
//! and does nothing when the hub isn't running.
//!
//! ```ignore
//! use limitless_link::{Action, Link};
//! let link = Link::new("color", "Limitless Color", "0.1.0",
//!     vec![Action::new("on", "Screen colors on"), Action::new("off", "Screen colors off")]);
//! link.start(
//!     |action, _args, _source| (true, format!("did {action}")),
//!     |_name, _value, _source| {},
//! );
//! link.state("filter", true.into());
//! ```
//! Protocol: shared/PROTOCOL.md.

use serde_json::{json, Map, Value};
use std::io::{BufRead, BufReader, Write};
use std::net::{Shutdown, TcpStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

pub const PROTOCOL: u64 = 1;

#[derive(Clone, Debug)]
pub struct Action {
    pub id: String,
    pub label: String,
    pub intent: Option<String>,
}

impl Action {
    pub fn new(id: &str, label: &str) -> Self {
        Self { id: id.into(), label: label.into(), intent: None }
    }
    pub fn intent(mut self, intent: &str) -> Self {
        self.intent = Some(intent.into());
        self
    }
    fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("id".into(), self.id.clone().into());
        m.insert("label".into(), self.label.clone().into());
        if let Some(i) = &self.intent {
            m.insert("intent".into(), i.clone().into());
        }
        Value::Object(m)
    }
}

/// The suite's shared folder, the same one the hub writes `link.json` to.
pub fn config_dir() -> PathBuf {
    if let Ok(p) = std::env::var("LIMITLESS_SOUND_HOME") {
        return PathBuf::from(p);
    }
    let home = std::env::var("HOME").or_else(|_| std::env::var("USERPROFILE")).unwrap_or_default();
    if cfg!(target_os = "macos") {
        PathBuf::from(home).join("Library/Application Support/Limitless Sound")
    } else if cfg!(windows) {
        let appdata = std::env::var("APPDATA").unwrap_or_else(|_| format!("{home}\\AppData\\Roaming"));
        PathBuf::from(appdata).join("Limitless Sound")
    } else {
        let base = std::env::var("XDG_CONFIG_HOME").unwrap_or_else(|_| format!("{home}/.config"));
        PathBuf::from(base).join("Limitless Sound")
    }
}

/// The installed Limitless Sound hub, if there is one.
pub fn hub_app() -> Option<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_default();
    let candidates: Vec<PathBuf> = if cfg!(target_os = "macos") {
        vec!["/Applications/Limitless Sound.app".into(), PathBuf::from(home).join("Applications/Limitless Sound.app")]
    } else if cfg!(windows) {
        std::env::var("LOCALAPPDATA")
            .map(|d| vec![PathBuf::from(d).join("Programs\\Limitless Sound\\Limitless Sound.exe")])
            .unwrap_or_default()
    } else {
        vec![]
    };
    candidates.into_iter().find(|p| p.exists())
}

/// Start the installed hub in the background. `true` if it was found.
pub fn launch_hub() -> bool {
    let Some(app) = hub_app() else { return false };
    let mut cmd = if cfg!(target_os = "macos") {
        let mut c = std::process::Command::new("open");
        c.args(["-g", "-j"]).arg(&app).args(["--args", "--background"]);
        c
    } else {
        let mut c = std::process::Command::new(&app);
        c.arg("--background");
        c
    };
    cmd.stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).spawn().is_ok()
}

type InvokeFn = dyn Fn(&str, &Value, &str) -> (bool, String) + Send + Sync;
type EventFn = dyn Fn(&str, &Value, &str) + Send + Sync;

struct Inner {
    tool: String,
    name: String,
    version: String,
    actions: Vec<Action>,
    stream: Mutex<Option<TcpStream>>,
    connected: AtomicBool,
    stopped: AtomicBool,
    one_voice: AtomicBool,
    /// The last value of each state, sent again whenever the link (re)connects.
    states: Mutex<Map<String, Value>>,
    depth: AtomicU64,
    ids: AtomicU64,
    retry: Duration,
}

#[derive(Clone)]
pub struct Link {
    inner: Arc<Inner>,
}

impl Link {
    pub fn new(tool: &str, name: &str, version: &str, actions: Vec<Action>) -> Self {
        Self {
            inner: Arc::new(Inner {
                tool: tool.into(),
                name: name.into(),
                version: version.into(),
                actions,
                stream: Mutex::new(None),
                connected: AtomicBool::new(false),
                stopped: AtomicBool::new(false),
                one_voice: AtomicBool::new(true),
                states: Mutex::new(Map::new()),
                depth: AtomicU64::new(0),
                ids: AtomicU64::new(1),
                retry: Duration::from_secs(2),
            }),
        }
    }

    /// Start the background thread. `on_invoke(action, args, source)` runs one of this
    /// app's actions; `on_event(name, value, source)` hears what happens in the suite.
    pub fn start<I, E>(&self, on_invoke: I, on_event: E)
    where
        I: Fn(&str, &Value, &str) -> (bool, String) + Send + Sync + 'static,
        E: Fn(&str, &Value, &str) + Send + Sync + 'static,
    {
        let inner = self.inner.clone();
        let on_invoke: Arc<InvokeFn> = Arc::new(on_invoke);
        let on_event: Arc<EventFn> = Arc::new(on_event);
        thread::Builder::new()
            .name("limitless-link".into())
            .spawn(move || {
                let mut tried_hub = false;
                while !inner.stopped.load(Ordering::SeqCst) {
                    let mut reached = false;
                    if let Some((port, token)) = read_link() {
                        reached = session(&inner, port, &token, &*on_invoke, &*on_event).is_ok();
                        close(&inner);
                    }
                    // Every app brings the suite up with it: open the hub if it's installed.
                    if !reached && !tried_hub {
                        tried_hub = true;
                        launch_hub();
                    }
                    thread::sleep(inner.retry);
                }
            })
            .expect("spawn limitless-link thread");
    }

    pub fn stop(&self) {
        self.inner.stopped.store(true, Ordering::SeqCst);
        close(&self.inner);
    }

    pub fn connected(&self) -> bool {
        self.inner.connected.load(Ordering::SeqCst)
    }

    /// Report that this app just did one of its actions (from any input).
    pub fn did(&self, action: &str, intent: Option<&str>) -> bool {
        let mut m = json!({"op": "did", "action": action, "depth": self.inner.depth.load(Ordering::SeqCst)});
        if let Some(i) = intent {
            m["intent"] = i.into();
        }
        send(&self.inner, &m)
    }

    /// Report a state change, e.g. `state("filter", true.into())`.
    /// Report a state ("on", true). Remembered, so the hub hears it again after reconnecting.
    pub fn state(&self, key: &str, value: Value) -> bool {
        self.inner.states.lock().unwrap().insert(key.to_string(), value.clone());
        send(&self.inner, &json!({"op": "state", "key": key, "value": value,
                                  "depth": self.inner.depth.load(Ordering::SeqCst)}))
    }

    /// Speak through the suite's one voice. `false` means speak for yourself.
    pub fn say(&self, text: &str) -> bool {
        self.connected() && self.inner.one_voice.load(Ordering::SeqCst) && send(&self.inner, &json!({"op": "say", "text": text}))
    }

    /// Ask the suite to do something (`"zoom.in"`, `"daw.record"`). `false` when the hub isn't there.
    pub fn invoke(&self, action: &str, args: Value) -> bool {
        let id = self.inner.ids.fetch_add(1, Ordering::SeqCst);
        send(&self.inner, &json!({"op": "invoke", "id": id, "action": action, "args": args,
                                  "depth": self.inner.depth.load(Ordering::SeqCst)}))
    }
}

fn read_link() -> Option<(u16, String)> {
    let text = std::fs::read_to_string(config_dir().join("link.json")).ok()?;
    let v: Value = serde_json::from_str(&text).ok()?;
    Some((v.get("port")?.as_u64()? as u16, v.get("token")?.as_str()?.to_string()))
}

fn send(inner: &Inner, msg: &Value) -> bool {
    let is_hello = msg.get("op").and_then(Value::as_str) == Some("hello");
    if !is_hello && !inner.connected.load(Ordering::SeqCst) {
        return false;
    }
    let mut guard = inner.stream.lock().unwrap();
    let Some(stream) = guard.as_mut() else { return false };
    let mut line = msg.to_string();
    line.push('\n');
    stream.write_all(line.as_bytes()).is_ok()
}

fn close(inner: &Inner) {
    if let Some(s) = inner.stream.lock().unwrap().take() {
        let _ = s.shutdown(Shutdown::Both);
    }
    inner.connected.store(false, Ordering::SeqCst);
}

fn session(inner: &Inner, port: u16, token: &str, on_invoke: &InvokeFn, on_event: &EventFn) -> std::io::Result<()> {
    let stream = TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_secs(2))?;
    stream.set_nodelay(true).ok();
    let reader = BufReader::new(stream.try_clone()?);
    *inner.stream.lock().unwrap() = Some(stream);
    let actions: Vec<Value> = inner.actions.iter().map(Action::to_json).collect();
    send(inner, &json!({"op": "hello", "protocol": PROTOCOL, "token": token, "tool": inner.tool,
                        "name": inner.name, "version": inner.version, "actions": actions}));
    for line in reader.lines() {
        let line = line?;
        let Ok(msg) = serde_json::from_str::<Value>(&line) else { continue };
        let op = msg.get("op").and_then(Value::as_str).unwrap_or("");
        match op {
            "welcome" | "prefs" => {
                let fresh = !inner.connected.swap(true, Ordering::SeqCst);
                let one = msg.pointer("/prefs/oneVoice").and_then(Value::as_bool).unwrap_or(true);
                inner.one_voice.store(one, Ordering::SeqCst);
                if fresh {
                    let states = inner.states.lock().unwrap().clone();
                    for (key, value) in states {
                        send(inner, &json!({"op": "state", "key": key, "value": value, "depth": 0}));
                    }
                }
            }
            "invoke" => {
                let action = msg.get("action").and_then(Value::as_str).unwrap_or("");
                let source = msg.get("source").and_then(Value::as_str).unwrap_or("");
                let args = msg.get("args").cloned().unwrap_or(Value::Null);
                inner.depth.store(msg.get("depth").and_then(Value::as_u64).unwrap_or(0), Ordering::SeqCst);
                let (ok, message) = on_invoke(action, &args, source);
                inner.depth.store(0, Ordering::SeqCst);
                send(inner, &json!({"op": "result", "id": msg.get("id"), "ok": ok, "message": message}));
            }
            "event" => {
                let name = msg.get("name").and_then(Value::as_str).unwrap_or("");
                let source = msg.get("source").and_then(Value::as_str).unwrap_or("");
                on_event(name, msg.get("value").unwrap_or(&Value::Null), source);
            }
            // A newer copy of this app took over: step aside for good instead of fighting it.
            "error" if msg.get("code").and_then(Value::as_str) == Some("replaced") => {
                inner.stopped.store(true, Ordering::SeqCst);
                return Ok(());
            }
            "error" if !inner.connected.load(Ordering::SeqCst) => return Ok(()),
            _ => {}
        }
    }
    Ok(())
}
