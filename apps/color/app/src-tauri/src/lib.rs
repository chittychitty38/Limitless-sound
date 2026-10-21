//! Limitless Color desktop app: the Color Tuner window, a menu bar / tray
//! switch, and the screen filter that applies the person's profile everywhere.

mod assistant;
mod filter;
mod store;

use std::sync::Mutex;

use color_core::helper::{offline_reply, HelperState, Suggestion};
use color_core::lut::{Lut3D, DEFAULT_SIZE};
use color_core::prompt::{self, Turn};
use color_core::Profile;
use serde::Serialize;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent, Wry};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

/// Toggles the screen filter from anywhere, with one hand.
const TOGGLE_SHORTCUT: &str = "CommandOrControl+Alt+C";

struct Inner {
    profile: Profile,
    filter_on: bool,
    filter: Box<dyn filter::ScreenFilter>,
    filter_note: String,
    helper: HelperState,
    history: Vec<Turn>,
    tray_check: Option<CheckMenuItem<Wry>>,
}

pub struct AppState(Mutex<Inner>);

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    profile: Profile,
    filter_on: bool,
    filter_kind: &'static str,
    filter_note: String,
    platform: &'static str,
    has_api_key: bool,
    shortcut: &'static str,
}

fn platform() -> &'static str {
    if cfg!(target_os = "macos") {
        "mac"
    } else if cfg!(windows) {
        "windows"
    } else {
        "other"
    }
}

fn status(inner: &Inner) -> Status {
    Status {
        profile: inner.profile.clone(),
        filter_on: inner.filter_on,
        filter_kind: inner.filter.kind(),
        filter_note: inner.filter_note.clone(),
        platform: platform(),
        has_api_key: assistant::api_key().is_some(),
        shortcut: TOGGLE_SHORTCUT,
    }
}

/// Pushes the current profile to the screen and remembers it.
fn sync(app: &AppHandle, inner: &mut Inner) {
    match inner.filter.apply(&inner.profile, inner.filter_on) {
        Ok(note) => inner.filter_note = note,
        Err(e) => {
            inner.filter_note = e;
        }
    }
    if let Some(c) = &inner.tray_check {
        let _ = c.set_checked(inner.filter_on);
    }
    store::save(app, &inner.profile, inner.filter_on);
    let _ = app.emit("status", status(inner));
}

fn toggle(app: &AppHandle) {
    let state = app.state::<AppState>();
    let mut inner = state.0.lock().unwrap();
    inner.filter_on = !inner.filter_on;
    sync(app, &mut inner);
}

#[tauri::command]
fn get_status(state: State<AppState>) -> Status {
    status(&state.0.lock().unwrap())
}

#[tauri::command]
fn set_profile(app: AppHandle, state: State<AppState>, profile: serde_json::Value) -> Result<Status, String> {
    let p = Profile::from_json(&profile.to_string()).map_err(|e| format!("That profile couldn't be read: {e}"))?;
    let mut inner = state.0.lock().unwrap();
    inner.profile = p;
    sync(&app, &mut inner);
    Ok(status(&inner))
}

#[tauri::command]
fn set_filter(app: AppHandle, state: State<AppState>, on: bool) -> Status {
    let mut inner = state.0.lock().unwrap();
    inner.filter_on = on;
    sync(&app, &mut inner);
    status(&inner)
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AssistantReply {
    reply: String,
    question: String,
    changes: Vec<String>,
    /// "claude" or "offline"
    source: &'static str,
    note: Option<String>,
    status: Status,
}

#[tauri::command]
async fn ask_assistant(app: AppHandle, state: State<'_, AppState>, message: String) -> Result<AssistantReply, String> {
    let (prompt_text, offline) = {
        let mut inner = state.0.lock().unwrap();
        let p = prompt::build(&inner.profile, &inner.history, &message);
        let profile = inner.profile.clone();
        let off = offline_reply(&message, &profile, &mut inner.helper);
        (p, off)
    };
    let mut note = None;
    let (suggestion, source) = match assistant::api_key() {
        Some(key) => match assistant::ask_claude(&key, prompt_text).await {
            Ok(text) => match Suggestion::from_model_text(&text) {
                Some(s) => (s, "claude"),
                None => {
                    note = Some("Claude's answer couldn't be read, so the built-in helper answered.".into());
                    (offline, "offline")
                }
            },
            Err(e) => {
                note = Some(format!("{e} The built-in helper answered instead."));
                (offline, "offline")
            }
        },
        None => (offline, "offline"),
    };
    let mut inner = state.0.lock().unwrap();
    let changes = suggestion.apply_to(&mut inner.profile);
    inner.history.push(Turn { from_person: true, text: message });
    inner.history.push(Turn {
        from_person: false,
        text: format!("{} {} [{}]", suggestion.reply, suggestion.question, changes.join("; ")),
    });
    sync(&app, &mut inner);
    Ok(AssistantReply { reply: suggestion.reply, question: suggestion.question, changes, source, note, status: status(&inner) })
}

#[tauri::command]
fn set_api_key(key: String) -> Result<bool, String> {
    assistant::set_api_key(key.trim())?;
    Ok(assistant::api_key().is_some())
}

#[tauri::command]
fn export_cube(app: AppHandle, state: State<AppState>) -> Result<String, String> {
    let profile = state.0.lock().unwrap().profile.clone();
    let dir = app.path().document_dir().map_err(|e| e.to_string())?.join("Limitless Color");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join("limitless-color.cube");
    std::fs::write(&path, Lut3D::from_profile(&profile, DEFAULT_SIZE).to_cube("Limitless Color profile")).map_err(|e| e.to_string())?;
    std::fs::write(dir.join("limitless-color-profile.json"), profile.to_json()).map_err(|e| e.to_string())?;
    Ok(path.display().to_string())
}

/// Starts the system's own dictation in the focused text box, so any microphone
/// the computer already uses works for talking to the assistant.
#[tauri::command]
fn start_dictation(app: AppHandle) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        app.run_on_main_thread(|| unsafe {
            use objc2::runtime::AnyObject;
            use objc2::{class, msg_send, sel};
            let ns_app: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];
            let none: *const AnyObject = std::ptr::null();
            let _: bool = msg_send![ns_app, sendAction: sel!(startDictation:), to: none, from: none];
        })
        .map_err(|e| e.to_string())?;
    }
    #[cfg(windows)]
    {
        let _ = &app;
        filter::windows::press_win_h();
    }
    #[cfg(not(any(target_os = "macos", windows)))]
    {
        let _ = &app;
    }
    Ok(())
}

fn build_tray(app: &AppHandle, filter_on: bool) -> tauri::Result<CheckMenuItem<Wry>> {
    let check = CheckMenuItem::with_id(app, "toggle", "Screen colors on", true, filter_on, None::<&str>)?;
    let open = MenuItem::with_id(app, "open", "Open Color Tuner…", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Limitless Color", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&check, &open, &PredefinedMenuItem::separator(app)?, &quit])?;
    TrayIconBuilder::with_id("main")
        .icon(app.default_window_icon().cloned().expect("app icon is bundled"))
        .tooltip("Limitless Color")
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "toggle" => toggle(app),
            "open" => show_tuner(app),
            "quit" => {
                let state = app.state::<AppState>();
                let mut inner = state.0.lock().unwrap();
                let profile = inner.profile.clone();
                let _ = inner.filter.apply(&profile, false);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(check)
}

fn show_tuner(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, Some(vec!["--background"])))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        toggle(app);
                    }
                })
                .build(),
        )
        .setup(|app| {
            let handle = app.handle().clone();
            let (profile, filter_on) = store::load(&handle);
            let filter = filter::create(&handle);
            let mut inner = Inner {
                profile,
                filter_on,
                filter,
                filter_note: String::new(),
                helper: HelperState::default(),
                history: vec![],
                tray_check: None,
            };
            inner.tray_check = Some(build_tray(&handle, filter_on)?);
            sync(&handle, &mut inner);
            app.manage(AppState(Mutex::new(inner)));
            if let Err(e) = app.global_shortcut().register(TOGGLE_SHORTCUT) {
                eprintln!("could not register {TOGGLE_SHORTCUT}: {e}");
            }
            // Started at login: stay in the menu bar / tray with the filter running.
            if std::env::args().any(|a| a == "--background") {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.hide();
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the tuner keeps the screen filter running; Quit is in the tray menu.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_status,
            set_profile,
            set_filter,
            ask_assistant,
            set_api_key,
            export_cube,
            start_dictation
        ])
        .run(tauri::generate_context!())
        .expect("Limitless Color failed to start");
}
