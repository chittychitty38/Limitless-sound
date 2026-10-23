//! Limitless Color desktop app: the Color Tuner window, a menu bar / tray
//! switch, and the screen filter that applies the person's profile everywhere.

mod applog;
mod assistant;
mod filter;
#[allow(dead_code)]
mod limitless_link;
mod store;
mod words;

use std::sync::{mpsc, Mutex, OnceLock};
use std::time::Duration;

use color_core::helper::{offline_reply_in, HelperState, Suggestion};
use color_core::lut::{Lut3D, DEFAULT_SIZE};
use color_core::prompt::{self, Turn};
use color_core::tune::{auto_tune, TuneResult};
use color_core::{CvdType, Lang, Profile, WindowPrefs};
use serde::Serialize;
use tauri::menu::{AboutMetadata, CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu, HELP_SUBMENU_ID, WINDOW_SUBMENU_ID};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent, Wry};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

use words::{t, tf};

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
    /// Text size, contrast and motion from the musician's shared settings (the hub).
    suite_prefs: WindowPrefs,
    /// The computer's own reduced-motion setting, which the window honored before the hub.
    system_prefs: WindowPrefs,
    /// The language the hub's shared settings chose, once it sends one.
    suite_language: Option<Lang>,
    /// The computer's own language, used until then.
    computer_language: Lang,
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
    window_prefs: WindowPrefs,
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
        window_prefs: window_prefs(inner),
    }
}

/// The language Color speaks: the suite's, else the computer's.
fn language(inner: &Inner) -> Lang {
    inner.suite_language.unwrap_or(inner.computer_language)
}

/// What the tuner window uses: the more accessible of the shared settings and the computer's own,
/// and the language in use.
fn window_prefs(inner: &Inner) -> WindowPrefs {
    WindowPrefs { language: language(inner), ..inner.suite_prefs.more_accessible(inner.system_prefs) }
}

/// Speaks the language in use everywhere outside the window, which follows it from
/// `window-prefs`: the tray or menu bar menu, the Mac's menus, the window's title, and the
/// screen filter's note. Runs on the main thread, where menus change.
fn relabel(app: &AppHandle, inner: &mut Inner) {
    if let (Some(tray), Ok((menu, check))) = (app.tray_by_id("main"), tray_menu(app, inner.filter_on)) {
        let _ = tray.set_menu(Some(menu));
        inner.tray_check = Some(check);
    }
    #[cfg(target_os = "macos")]
    if let Ok(menu) = app_menu(app) {
        let _ = app.set_menu(menu);
    }
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.set_title(&t("Limitless Color Tuner"));
    }
    sync(app, inner);
}

/// Sends the window prefs to the tuner window (hidden or not, so it's ready when shown)
/// and tells the suite which are in use.
fn show_window_prefs(app: &AppHandle, inner: &Inner) {
    let prefs = window_prefs(inner);
    let _ = app.emit("window-prefs", prefs);
    if let Some(link) = SUITE.get() {
        link.state("prefs.applied", prefs.applied());
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
            if e != inner.filter_note {
                applog::error(&format!("The screen filter couldn't be applied: {e}"));
            }
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
    // The suite talks English: the hub and the other apps translate the labels they show
    // (Limitless Voice listens for them in English and in its own language).
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
    link.on_prefs(move |prefs| {
        let state = handle.state::<AppState>();
        let mut inner = state.0.lock().unwrap();
        inner.suite_prefs = WindowPrefs::from_prefs(prefs);
        if let Some(l) = WindowPrefs::suite_language(prefs) {
            inner.suite_language = Some(l);
        }
        if words::set(language(&inner)) {
            // Menus change on the main thread, which may be waiting for this lock: let go first.
            let main = handle.clone();
            let _ = handle.run_on_main_thread(move || {
                let state = main.state::<AppState>();
                let mut inner = state.0.lock().unwrap();
                relabel(&main, &mut inner);
            });
        }
        show_window_prefs(&handle, &inner);
    });
    let on = app.state::<AppState>().0.lock().unwrap().filter_on;
    link.state("on", on.into());
    // Set before starting, so the first prefs from the hub can be answered.
    let _ = SUITE.set(link.clone());
    let handle = app.clone();
    link.start(move |action, _args, _source| suite_invoke(&handle, action), |_name, _value, _source| {});
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
                (true, t(if inner.filter_on { "Screen colors on" } else { "Screen colors off" }))
            }
            "tuner" => {
                show_tuner(&handle);
                (true, t("Opened the color tuner"))
            }
            other => (false, tf("Limitless Color has no action {action}.", &[("action", &quote(other))])),
        };
        let _ = tx.send(result);
    });
    if queued.is_err() {
        return (false, t("Limitless Color is closing."));
    }
    rx.recv_timeout(Duration::from_secs(3)).unwrap_or_else(|_| (false, t("Limitless Color didn't answer.")))
}

/// Words quoted the way the language in use quotes them: 'record' or «record».
fn quote(text: &str) -> String {
    match words::current() {
        Lang::En => format!("'{text}'"),
        Lang::Es => format!("«{text}»"),
    }
}

/// The shortcut and the tray switch. With the window out of sight, the suite's one voice says
/// what happened (when the musician has spoken feedback on), in Color's language: the hub reads
/// it with a voice for the language Color reports in `prefs.applied`.
fn toggle(app: &AppHandle) {
    let state = app.state::<AppState>();
    let mut inner = state.0.lock().unwrap();
    inner.filter_on = !inner.filter_on;
    sync(app, &mut inner);
    if let Some(link) = SUITE.get() {
        link.say(&t(if inner.filter_on { "Screen colors on" } else { "Screen colors off" }));
    }
}

#[tauri::command]
fn get_status(app: AppHandle, state: State<AppState>) -> Status {
    full_status(&app, &state.0.lock().unwrap())
}

#[tauri::command]
fn set_profile(app: AppHandle, state: State<AppState>, profile: serde_json::Value) -> Result<Status, String> {
    let p = Profile::from_json(&profile.to_string()).map_err(|e| tf("That profile couldn't be read: {error}", &[("error", &e.to_string())]))?;
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
    // Both answer in the window's language; the built-in helper understands English and Spanish.
    let (prompt_text, offline, lang) = {
        let mut inner = state.0.lock().unwrap();
        let lang = language(&inner);
        let p = prompt::build_in(&inner.profile, &inner.history, &message, lang);
        let profile = inner.profile.clone();
        let off = offline_reply_in(&message, &profile, &mut inner.helper, lang);
        (p, off, lang)
    };
    let mut note = None;
    let (suggestion, source) = match assistant::api_key() {
        Some(key) => match assistant::ask_claude(&key, prompt_text).await {
            Ok(text) => match Suggestion::from_model_text(&text) {
                Some(s) => (s, "claude"),
                None => {
                    note = Some(t("Claude's answer couldn't be read, so the built-in helper answered."));
                    (offline, "offline")
                }
            },
            Err(e) => {
                note = Some(tf("{problem} The built-in helper answered instead.", &[("problem", &e)]));
                (offline, "offline")
            }
        },
        None => (offline, "offline"),
    };
    let mut inner = state.0.lock().unwrap();
    let changes = suggestion.apply_in(&mut inner.profile, lang);
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

/// The computer's own reduced-motion setting, as the window sees it.
#[tauri::command]
fn set_system_motion(app: AppHandle, state: State<AppState>, reduce: bool) {
    let mut inner = state.0.lock().unwrap();
    inner.system_prefs.reduce_motion = reduce;
    show_window_prefs(&app, &inner);
}

#[tauri::command]
fn set_autostart(app: AppHandle, state: State<AppState>, on: bool) -> Result<Status, String> {
    let al = app.autolaunch();
    if on { al.enable() } else { al.disable() }.map_err(|e| tf("Couldn't change start at login: {error}", &[("error", &e.to_string())]))?;
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

/// The Mac's menu bar while the tuner window is open: Tauri's usual one, in the language in use.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn app_menu(app: &AppHandle) -> tauri::Result<Menu<Wry>> {
    let name = [("name", "Limitless Color")];
    let about = AboutMetadata {
        name: Some("Limitless Color".into()),
        version: Some(app.package_info().version.to_string()),
        ..Default::default()
    };
    Menu::with_items(
        app,
        &[
            &Submenu::with_items(
                app,
                "Limitless Color",
                true,
                &[
                    &PredefinedMenuItem::about(app, Some(&tf("About {name}", &name)), Some(about))?,
                    &PredefinedMenuItem::separator(app)?,
                    &PredefinedMenuItem::services(app, Some(&t("Services")))?,
                    &PredefinedMenuItem::separator(app)?,
                    &PredefinedMenuItem::hide(app, Some(&tf("Hide {name}", &name)))?,
                    &PredefinedMenuItem::hide_others(app, Some(&t("Hide Others")))?,
                    &PredefinedMenuItem::separator(app)?,
                    &PredefinedMenuItem::quit(app, Some(&tf("Quit {name}", &name)))?,
                ],
            )?,
            &Submenu::with_items(app, t("File"), true, &[&PredefinedMenuItem::close_window(app, Some(&t("Close Window")))?])?,
            &Submenu::with_items(
                app,
                t("Edit"),
                true,
                &[
                    &PredefinedMenuItem::undo(app, Some(&t("Undo")))?,
                    &PredefinedMenuItem::redo(app, Some(&t("Redo")))?,
                    &PredefinedMenuItem::separator(app)?,
                    &PredefinedMenuItem::cut(app, Some(&t("Cut")))?,
                    &PredefinedMenuItem::copy(app, Some(&t("Copy")))?,
                    &PredefinedMenuItem::paste(app, Some(&t("Paste")))?,
                    &PredefinedMenuItem::select_all(app, Some(&t("Select All")))?,
                ],
            )?,
            &Submenu::with_items(app, t("View"), true, &[&PredefinedMenuItem::fullscreen(app, Some(&t("Enter Full Screen")))?])?,
            &Submenu::with_id_and_items(
                app,
                WINDOW_SUBMENU_ID,
                t("Window"),
                true,
                &[
                    &PredefinedMenuItem::minimize(app, Some(&t("Minimize")))?,
                    &PredefinedMenuItem::maximize(app, Some(&t("Zoom")))?,
                    &PredefinedMenuItem::separator(app)?,
                    &PredefinedMenuItem::close_window(app, Some(&t("Close Window")))?,
                ],
            )?,
            &Submenu::with_id_and_items(app, HELP_SUBMENU_ID, t("Help"), true, &[])?,
        ],
    )
}

/// The menu bar (Mac) or tray (Windows) menu in the language in use, and its switch.
fn tray_menu(app: &AppHandle, filter_on: bool) -> tauri::Result<(Menu<Wry>, CheckMenuItem<Wry>)> {
    let check = CheckMenuItem::with_id(app, "toggle", t("Screen colors on"), true, filter_on, None::<&str>)?;
    let open = MenuItem::with_id(app, "open", t("Open Color Tuner…"), true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", t("Quit Limitless Color"), true, None::<&str>)?;
    Ok((Menu::with_items(app, &[&check, &open, &PredefinedMenuItem::separator(app)?, &quit])?, check))
}

fn build_tray(app: &AppHandle, filter_on: bool) -> tauri::Result<CheckMenuItem<Wry>> {
    let (menu, check) = tray_menu(app, filter_on)?;
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
    // Limitless Color.log in the suite's log folder: what went wrong, when nobody was watching.
    applog::start("Limitless Color", env!("CARGO_PKG_VERSION"));
    // Until the hub says otherwise, the computer's language.
    let computer_language = words::computer_language();
    words::set(computer_language);
    let builder = tauri::Builder::default();
    #[cfg(target_os = "macos")]
    let builder = builder.menu(app_menu);
    builder
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
        .setup(move |app| {
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
                suite_prefs: WindowPrefs::default(),
                system_prefs: WindowPrefs::default(),
                suite_language: None,
                computer_language,
            };
            inner.tray_check = Some(build_tray(&handle, filter_on)?);
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_title(&t("Limitless Color Tuner"));
            }
            sync(&handle, &mut inner);
            app.manage(AppState(Mutex::new(inner)));
            start_suite(&handle);
            if let Err(e) = app.global_shortcut().register(TOGGLE_SHORTCUT) {
                applog::warn(&format!("Couldn't register the shortcut {TOGGLE_SHORTCUT}: {e}"));
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
            set_system_motion,
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
