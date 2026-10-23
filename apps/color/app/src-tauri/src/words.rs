//! Limitless Color's language: the suite's (`language` in the Limitless Sound hub's shared
//! settings) once the hub sends it, the computer's own until then. Everything the app shows or
//! says, from the tray menu to its answers to other apps, goes through [`t`]. The Spanish is the
//! tuner window's own table (color_core::lang).

use std::sync::atomic::{AtomicU8, Ordering};

use color_core::lang::{self, Lang};

/// The language in use: 0 English, 1 Spanish.
static CURRENT: AtomicU8 = AtomicU8::new(0);

pub fn current() -> Lang {
    match CURRENT.load(Ordering::SeqCst) {
        1 => Lang::Es,
        _ => Lang::En,
    }
}

/// Uses `language` from now on. True when that's a change.
pub fn set(language: Lang) -> bool {
    let code = match language {
        Lang::En => 0,
        Lang::Es => 1,
    };
    CURRENT.swap(code, Ordering::SeqCst) != code
}

/// `en` in the language in use.
pub fn t(en: &str) -> String {
    lang::t(current(), en)
}

/// [`t`], with each `{name}` in it filled in.
pub fn tf(en: &str, vars: &[(&str, &str)]) -> String {
    lang::tf(current(), en, vars)
}

/// The computer's own language, when Color has it; English otherwise.
pub fn computer_language() -> Lang {
    Lang::first_of(&computer_languages())
}

/// The languages the person chose for the Mac, most preferred first.
#[cfg(target_os = "macos")]
fn computer_languages() -> Vec<String> {
    // As the hub reads them (shared/hub/limitless_hub/languages.py).
    let Ok(out) = std::process::Command::new("defaults").args(["read", "-g", "AppleLanguages"]).output() else {
        return vec![];
    };
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(|l| l.trim().trim_matches(|c| c == '"' || c == ',').to_string())
        .filter(|l| !l.is_empty() && l != "(" && l != ")")
        .collect()
}

/// Windows' display language.
#[cfg(windows)]
fn computer_languages() -> Vec<String> {
    let id = unsafe { windows::Win32::Globalization::GetUserDefaultUILanguage() };
    // The primary language of a LANGID: 0x09 English, 0x0a Spanish.
    vec![match id & 0x3ff {
        0x0a => "es".to_string(),
        0x09 => "en".to_string(),
        _ => String::new(),
    }]
}

#[cfg(not(any(target_os = "macos", windows)))]
fn computer_languages() -> Vec<String> {
    ["LC_ALL", "LC_MESSAGES", "LANG"].iter().filter_map(|k| std::env::var(k).ok()).filter(|v| !v.is_empty()).collect()
}
