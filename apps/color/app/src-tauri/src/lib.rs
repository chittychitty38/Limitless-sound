//! Limitless Color desktop app: the Color Tuner window, a menu bar / tray
//! switch, and the screen filter that applies the person's profile everywhere.

mod assistant;
mod filter;
#[allow(dead_code)]
mod limitless_link;
mod store;

use std::sync::{mpsc, Mutex, OnceLock};
use std::time::Duration;

use color_core::helper::{offline_reply, HelperState, Suggestion};
use color_core::lut::{Lut3D, DEFAULT_SIZE};
use color_core::prompt::{self, Turn};
use color_core::tune::{auto_tune, TuneResult};
use color_core::{CvdType, Profile};
use serde::Serialize;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent, Wry};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

/// Toggles the screen filter from anywhere, with one hand.
const TOGGLE_SHORTCUT: &str = "CommandOrControl+Alt+C";

/// The link to the Limitless Sound hub, once it has started.
static SUITE: OnceLock<limitless_link::Link> = OnceLock::new();

struct Inner {
    profile: Profile,
    filter_on: bool,
    filter: Box<dyn filter::ScreenFilter>,
    filter_note: String,
    helper: HelperState,
    history: Vec<Turn>,
    tray_check: Option<CheckMenuItem<Wry>>,
    /// First-launch progress: "" (not started), a step name, or "done".
    onboarding: String,
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
    onboarding: String,
    autostart: bool,
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
        onboarding: inner.onboarding.clone(),
        autostart: false,
    }
}

fn full_status(app: &AppHandle, inner: &Inner) -> Status {
    let mut st = status(inner);
    st.autostart = app.autolaunch().is_enabled().unwrap_or(false);
    st
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
    store::save(app, &inner.profile, inner.filter_on, &inner.onboarding);
    if let Some(link) = SUITE.get() {
        link.state("on", inner.filter_on.into());
    }
    let _ = app.emit("status", full_status(app, inner));
}

/// Joins the Limitless Sound hub when it runs, so Voice, the controller, a Stream Deck
/// or a link ("colors follow the DAW") can switch the screen colors.
fn start_suite(app: &AppHandle) {
    use limitless_link::{Action, Link};
    let link = Link::new(
        "color",
        "Limitless Color",
        &app.package_info().version.to_string(),
        vec![
            Action::new("on", "Screen colors on"),
            Action::new("off", "Screen colors off"),
            Action::new("toggle", "Screen colors on or off"),
            Action::new("tuner", "Open the color tuner"),
        ],
    );
    let handle = app.clone();
    link.start(move |action, _args, _source| suite_invoke(&handle, action), |_name, _value, _source| {});
    let on = app.state::<AppState>().0.lock().unwrap().filter_on;
    link.state("on", on.into());
    let _ = SUITE.set(link);
}

/// Runs a suite action on the main thread, where the screen filter lives.
fn suite_invoke(app: &AppHandle, action: &str) -> (bool, String) {
    let (tx, rx) = mpsc::channel();
    let handle = app.clone();
    let action = action.to_string();
    let queued = app.run_on_main_thread(move || {
        let result = match action.as_str() {
            "on" | "off" | "toggle" => {
                let state = handle.state::<AppState>();
                let mut inner = state.0.lock().unwrap();
                inner.filter_on = match action.as_str() {
                    "on" => true,
                    "off" => false,
                    _ => !inner.filter_on,
                };
                sync(&handle, &mut inner);
                let said = if inner.filter_on { "Screen colors on" } else { "Screen colors off" };
                (true, said.to_string())
            }
            "tuner" => {
                show_tuner(&handle);
                (true, "Opened the color tuner".to_string())
            }
            other => (false, format!("Limitless Color has no action '{other}'.")),
        };
        let _ = tx.send(result);
    });
    if queued.is_err() {
        return (false, "Limitless Color is closing.".into());
    }
    rx.recv_timeout(Duration::from_secs(3))
        .unwrap_or_else(|_| (false, "Limitless Color didn't answer.".into()))
}

fn toggle(app: &AppHandle) {
    let state = app.state::<AppState>();
    let mut inner = state.0.lock().unwrap();
    inner.filter_on = !inner.filter_on;
    sync(app, &mut inner);
}

#[tauri::command]
fn get_status(app: AppHandle, state: State<AppState>) -> Status {
    full_status(&app, &state.0.lock().unwrap())
}

#[tauri::command]
fn set_profile(app: AppHandle, state: State<AppState>, profile: serde_json::Value) -> Result<Status, String> {
    let p = Profile::from_json(&profile.to_string()).map_err(|e| format!("That profile couldn't be read: {e}"))?;
    let mut inner = state.0.lock().unwrap();
    if inner.profile == p {
        // Nothing changed: don't save the file, rebuild the filter or redraw the window again.
        return Ok(status(&inner));
    }
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

/// "Make it clear for me": finds the clearest natural-looking profile for this
/// kind and strength of color vision. The window previews it before applying.
#[tauri::command]
async fn auto_tune_profile(cvd: CvdType, severity: f64) -> Result<TuneResult, String> {
    tauri::async_runtime::spawn_blocking(move || auto_tune(cvd, severity)).await.map_err(|e| e.to_string())
}

#[tauri::command]
fn set_onboarding(app: AppHandle, state: State<AppState>, step: String) -> Status {
    let mut inner = state.0.lock().unwrap();
    inner.onboarding = step;
    store::save(&app, &inner.profile, inner.filter_on, &inner.onboarding);
    full_status(&app, &inner)
}

#[tauri::command]
fn set_autostart(app: AppHandle, state: State<AppState>, on: bool) -> Result<Status, String> {
    let al = app.autolaunch();
    if on { al.enable() } else { al.disable() }.map_err(|e| format!("Couldn't change start at login: {e}"))?;
    Ok(full_status(&app, &state.0.lock().unwrap()))
}

/// Screen Recording permission on Mac: "granted", "denied", or "not-needed" elsewhere.
#[tauri::command]
async fn screen_permission(app: AppHandle, request: bool) -> Result<&'static str, String> {
    #[cfg(target_os = "macos")]
    {
        let ok = filter::macos::screen_permission(&app, request).await?;
        return Ok(if ok { "granted" } else { "denied" });
    }
    #[allow(unreachable_code)]
    {
        let _ = (app, request);
        Ok("not-needed")
    }
}

/// Opens the system settings page where Screen Recording is allowed.
#[tauri::command]
fn open_screen_settings() -> Result<(), String> {
    #[cfg(target_os = "macos")]
    std::process::Command::new("open")
        .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Starts the screen filter from scratch, for example once permission was granted.
#[tauri::command]
fn restart_filter(app: AppHandle, state: State<AppState>) -> Status {
    let mut inner = state.0.lock().unwrap();
    inner.filter.restart();
    sync(&app, &mut inner);
    full_status(&app, &inner)
}

/// Quits and opens the app again (macOS sometimes needs this after a permission change).
#[tauri::command]
fn relaunch(app: AppHandle) {
    app.restart();
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
    // Mac: a monochrome icon that matches the menu bar. Windows: the color app icon.
    #[cfg(target_os = "macos")]
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/tray-template.png"))?;
    #[cfg(not(target_os = "macos"))]
    let icon = app.default_window_icon().cloned().expect("app icon is bundled");
    TrayIconBuilder::with_id("main")
        .icon(icon)
        .icon_as_template(cfg!(target_os = "macos"))
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
                if let Some(link) = SUITE.get() {
                    link.stop();
                }
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(check)
}

fn show_tuner(app: &AppHandle) {
    // The Dock icon shows only while the window is open; the rest of the time
    // Limitless Color lives in the menu bar.
    #[cfg(target_os = "macos")]
    let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn hide_tuner(window: &tauri::Window) {
    let _ = window.hide();
    #[cfg(target_os = "macos")]
    let _ = window.app_handle().set_activation_policy(tauri::ActivationPolicy::Accessory);
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
            let saved = store::load(&handle);
            let filter_on = saved.filter_on;
            let filter = filter::create(&handle);
            let mut inner = Inner {
                profile: saved.profile,
                filter_on,
                filter,
                filter_note: String::new(),
                helper: HelperState::default(),
                history: vec![],
                tray_check: None,
                onboarding: saved.onboarding,
            };
            inner.tray_check = Some(build_tray(&handle, filter_on)?);
            sync(&handle, &mut inner);
            app.manage(AppState(Mutex::new(inner)));
            start_suite(&handle);
            if let Err(e) = app.global_shortcut().register(TOGGLE_SHORTCUT) {
                eprintln!("could not register {TOGGLE_SHORTCUT}: {e}");
            }
            // Started at login: stay in the menu bar / tray with the filter running.
            // Before first-launch setup is finished, always show the window.
            let finished = app.state::<AppState>().0.lock().unwrap().onboarding == "done";
            if finished && std::env::args().any(|a| a == "--background") {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.hide();
                }
                #[cfg(target_os = "macos")]
                app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the tuner keeps the screen filter running; Quit is in the tray menu.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                hide_tuner(window);
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_status,
            set_profile,
            set_filter,
            ask_assistant,
            set_api_key,
            export_cube,
            start_dictation,
            auto_tune_profile,
            set_onboarding,
            set_autostart,
            screen_permission,
            open_screen_settings,
            restart_filter,
            relaunch
        ])
        .build(tauri::generate_context!())
        .expect("Limitless Color failed to start")
        .run(|app, event| {
            // Opening the app again from Finder or Launchpad while it runs in the menu bar.
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen { .. } = event {
                show_tuner(app);
            }
            let _ = (app, event);
        });
}
