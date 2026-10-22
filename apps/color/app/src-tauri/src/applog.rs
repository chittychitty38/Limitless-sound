//! A log file for a Limitless Sound app written in Rust, so a problem can be found after the
//! fact. The same folder and lines as the Python and JavaScript apps' applog:
//!
//!   Mac      ~/Library/Logs/Limitless Sound/<App>.log
//!   Windows  %LOCALAPPDATA%\Limitless Sound\Logs\<App>.log
//!   Linux    ~/.local/state/Limitless Sound/<App>.log
//!
//! A packaged app has no console, so without this a panic leaves no trace. This keeps the
//! newest megabyte (plus one older file, <App>.log.1) and records every panic, in any thread,
//! before the app handles it as it always would. The log never leaves the computer; a musician
//! can send it when asking for help. Times are UTC: the standard library can't read the
//! computer's time zone, and the first line says so.
//!
//! Copy this file into the app (next to limitless_link.rs) and start it first thing:
//!
//! ```ignore
//! applog::start("Limitless Color", env!("CARGO_PKG_VERSION"));
//! applog::warn(&format!("could not register {shortcut}: {e}"));
//! ```
//!
//! Standard library only.

#![allow(dead_code)]

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

pub const KEEP_BYTES: u64 = 1024 * 1024;

struct Log {
    app: String,
    file: PathBuf,
    size: u64,
}

static LOG: OnceLock<Mutex<Log>> = OnceLock::new();

/// The folder every Limitless Sound app writes its log to.
pub fn log_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("LIMITLESS_SOUND_LOGS").filter(|d| !d.is_empty()) {
        return PathBuf::from(dir);
    }
    let home = || {
        PathBuf::from(
            std::env::var_os("HOME")
                .or_else(|| std::env::var_os("USERPROFILE"))
                .unwrap_or_default(),
        )
    };
    if cfg!(target_os = "macos") {
        return home().join("Library").join("Logs").join("Limitless Sound");
    }
    if cfg!(windows) {
        let base = std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home().join("AppData").join("Local"));
        return base.join("Limitless Sound").join("Logs");
    }
    let state = std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".local").join("state"));
    state.join("Limitless Sound")
}

/// A UTC time as Python's logging writes local time: 2026-10-22 11:29:13,123
pub fn stamp_at(unix_ms: u128) -> String {
    let secs = (unix_ms / 1000) as i64;
    let (days, rem) = (secs.div_euclid(86_400), secs.rem_euclid(86_400));
    // Days since 1970-01-01 to a calendar date (Howard Hinnant's civil_from_days).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02} {:02}:{:02}:{:02},{:03}",
        rem / 3600,
        rem % 3600 / 60,
        rem % 60,
        unix_ms % 1000
    )
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

/// Writes one line. Does nothing before start(), or if the file can't be written.
pub fn write(level: &str, message: &str) {
    let Some(log) = LOG.get() else { return };
    let mut log = log.lock().unwrap_or_else(|e| e.into_inner());
    let line = format!("{} {level:<7} {}: {message}\n", stamp_at(now_ms()), log.app);
    let bytes = line.len() as u64;
    if log.size > 0 && log.size + bytes >= KEEP_BYTES {
        let mut older = log.file.clone().into_os_string();
        older.push(".1");
        let _ = fs::remove_file(&older);
        if fs::rename(&log.file, &older).is_ok() {
            log.size = 0;
        }
    }
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&log.file) {
        if f.write_all(line.as_bytes()).is_ok() {
            log.size += bytes;
        }
    }
}

pub fn info(message: &str) {
    write("INFO", message);
}
pub fn warn(message: &str) {
    write("WARNING", message);
}
pub fn error(message: &str) {
    write("ERROR", message);
}

fn system() -> String {
    // macOS keeps its version in a plain file; elsewhere the name is enough to go on.
    if cfg!(target_os = "macos") {
        if let Ok(plist) = fs::read_to_string("/System/Library/CoreServices/SystemVersion.plist") {
            if let Some(v) = plist
                .split("<key>ProductVersion</key>")
                .nth(1)
                .and_then(|r| r.split("<string>").nth(1))
                .and_then(|r| r.split("</string>").next())
            {
                return format!("macOS {v}");
            }
        }
        return "macOS".into();
    }
    match std::env::consts::OS {
        "windows" => "Windows".into(),
        "linux" => "Linux".into(),
        other => other.into(),
    }
}

/// Starts logging for this app. Returns the log file, or None if it can't be written.
pub fn start(app: &str, version: &str) -> Option<PathBuf> {
    let folder = log_dir();
    fs::create_dir_all(&folder).ok()?;
    let file = folder.join(format!("{app}.log"));
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file)
        .ok()?;
    let size = fs::metadata(&file).map(|m| m.len()).unwrap_or(0);
    if LOG
        .set(Mutex::new(Log {
            app: app.into(),
            file: file.clone(),
            size,
        }))
        .is_err()
    {
        return Some(file); // already started
    }
    // Panics, on any thread, get written down; then the app handles them as it always would.
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let thread = std::thread::current();
        let backtrace = std::backtrace::Backtrace::force_capture();
        write(
            "CRITICAL",
            &format!(
                "Panic in thread {}: {info}\n{backtrace}",
                thread.name().unwrap_or("?")
            ),
        );
        previous(info);
    }));
    info(&format!(
        "Started {app} {version} on {} ({}), Rust, times in UTC",
        system(),
        std::env::consts::ARCH
    ));
    Some(file)
}
